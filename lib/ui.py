#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Interface graphique du plugin (GTK 3 via GimpUi).

.. note:: **À propos de GTK 3 vs GTK 4**

   GIMP 3.2.x est une application **GTK 3** : son module ``GimpUi`` est lié à
   ``Gtk-3.0`` (vérifiable dans la typelib). Un même processus ne pouvant
   charger simultanément GTK 3 et GTK 4, l'interface d'un plugin GIMP 3.2 doit
   impérativement utiliser **GTK 3**. Le code ci-dessous s'appuie donc sur GTK 3,
   tout en visant un rendu moderne (fenêtre à en-tête, onglets, contrôles
   cohérents). Le portage GTK 4 n'aura de sens que lorsque GIMP lui-même
   migrera vers GTK 4.

Cette interface :

* collecte tous les réglages du filigrane et de l'export ;
* valide les saisies avant de lancer le traitement ;
* affiche une barre de progression et un journal des résultats **sans jamais
  figer l'interface**.

.. important:: **Pourquoi l'export n'est pas lancé d'un seul bloc**

   Traiter tout le lot à l'intérieur du gestionnaire de signal ``response``
   monopolise la boucle principale GTK pendant toute la durée du lot. La
   fenêtre ne répond alors plus aux requêtes du gestionnaire de fenêtres
   (``_NET_WM_PING``), qui la déclare « ne répond pas » et propose de la tuer —
   alors même que l'export se déroule correctement. Pomper la file d'événements
   entre deux images ne suffit pas : une seule grande image (filigrane, fusion,
   puis compression PNG) dépasse largement le délai de grâce du gestionnaire de
   fenêtres.

   L'export est donc découpé : le moteur expose un **générateur** (une image par
   itération) que cette fenêtre fait avancer depuis la boucle GTK elle-même
   (``GLib.timeout_add``). Entre deux images, la boucle reprend la main
   normalement ; à l'intérieur d'une image, les rappels d'étape pompent la file
   d'événements. La fenêtre reste vivante, l'annulation devient possible.

L'interface est **découplée** du moteur d'export : elle reçoit un *export
runner* (callable) en injection de dépendance, ce qui facilite les tests et
respecte l'inversion de dépendance.
"""

from __future__ import annotations

from typing import Callable, Iterator, List, Optional

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gimp, GimpUi, GLib, Gtk  # noqa: E402

from . import constants as C  # noqa: E402
from . import utils  # noqa: E402
from .constants import (  # noqa: E402
    ExportFormat,
    NamingMode,
    Position,
    SizeMode,
    WatermarkType,
)
from .logger import get_logger  # noqa: E402
from .settings import Settings, SettingsManager  # noqa: E402

_log = get_logger("ui")


def _(message: str) -> str:
    """Fonction de traduction (passe-plat ; point d'ancrage i18n futur)."""
    return message


#: Signature d'un exécuteur d'export injecté dans le dialogue. Il reçoit les
#: préférences, un rappel de progression ``(index, total, nom, statut)`` et un
#: rappel d'étape ``(libellé)``, et retourne un **itérateur** produisant un
#: résultat par image (voir :meth:`lib.exporter.BatchExporter.iter_export`).
ExportRunner = Callable[
    [Settings, Callable[[int, int, str, str], None], Callable[[str], None]],
    Iterator,
]


# ---------------------------------------------------------------------------
# Helpers couleur GTK <-> hex
# ---------------------------------------------------------------------------

def _rgba_from_hex(hex_color: str) -> Gdk.RGBA:
    """Convertit ``#rrggbb`` en :class:`Gdk.RGBA` (opaque)."""
    rgba = Gdk.RGBA()
    if not rgba.parse(hex_color or "#000000"):
        rgba.parse("#000000")
    return rgba


def _hex_from_rgba(rgba: Gdk.RGBA) -> str:
    """Convertit un :class:`Gdk.RGBA` en chaîne ``#rrggbb``."""
    return "#{:02x}{:02x}{:02x}".format(
        int(round(rgba.red * 255)),
        int(round(rgba.green * 255)),
        int(round(rgba.blue * 255)),
    )


# ---------------------------------------------------------------------------
# Dialogue principal
# ---------------------------------------------------------------------------

class WatermarkDialog:
    """Fenêtre de configuration et de lancement de l'export.

    :param settings: préférences initiales (chargées depuis le disque).
    :param settings_manager: gestionnaire de persistance des préférences.
    :param export_runner: callable exécutant l'export ; reçoit ``(settings,
        progress_callback)`` et retourne une liste de résultats possédant les
        attributs ``success``, ``image_name`` et ``error_message``.
    :param image_count: nombre d'images ouvertes (pour information).
    """

    def __init__(self, settings: Settings, settings_manager: SettingsManager,
                 export_runner: ExportRunner, image_count: int) -> None:
        self._settings = settings
        self._manager = settings_manager
        self._export_runner = export_runner
        self._image_count = image_count
        self._running = False
        self._cancel_requested = False
        self._export_iter: Optional[Iterator] = None
        self._results: List = []
        self._step_source: int = 0

        self.dialog: Gtk.Dialog = GimpUi.Dialog(
            title=C.PLUGIN_TITLE,
            role=C.PLUGIN_ID,
            use_header_bar=True,
        )
        self.dialog.set_default_size(560, 640)
        self._cancel_button = self.dialog.add_button(_("Annuler"), Gtk.ResponseType.CANCEL)
        self._export_button = self.dialog.add_button(_("Exporter"), Gtk.ResponseType.OK)
        self._export_button.get_style_context().add_class("suggested-action")

        self._build_ui()
        self._load_settings_into_widgets()
        self._update_sensitivity()

    # ------------------------------------------------------------------ #
    # Construction de l'interface
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        """Assemble la totalité des widgets de la fenêtre."""
        content = self.dialog.get_content_area()
        content.set_spacing(8)
        content.set_border_width(8)

        # Bandeau d'information sur le nombre d'images.
        info = Gtk.Label()
        info.set_xalign(0.0)
        plural = "s" if self._image_count > 1 else ""
        info.set_markup(
            f"<b>{self._image_count}</b> image{plural} ouverte{plural} "
            f"seront traitées. Les originaux ne seront pas modifiés."
        )
        content.pack_start(info, False, False, 0)

        notebook = Gtk.Notebook()
        notebook.append_page(self._build_watermark_page(), Gtk.Label(label=_("Filigrane")))
        notebook.append_page(self._build_export_page(), Gtk.Label(label=_("Export")))
        content.pack_start(notebook, True, True, 0)

        # Zone de progression.
        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_show_text(True)
        self._progress_bar.set_text(_("En attente"))
        content.pack_start(self._progress_bar, False, False, 0)

        # Journal des résultats (défilable).
        self._log_buffer = Gtk.TextBuffer()
        log_view = Gtk.TextView(buffer=self._log_buffer)
        log_view.set_editable(False)
        log_view.set_cursor_visible(False)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(90)
        scroller.add(log_view)
        content.pack_start(scroller, False, False, 0)

    # -- Onglet Filigrane -------------------------------------------------
    def _build_watermark_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.set_border_width(8)

        # --- Type de filigrane ---
        type_frame, type_grid = self._make_frame(_("Type de filigrane"))
        self._radio_image = Gtk.RadioButton.new_with_label(None, _("Image (logo PNG)"))
        self._radio_text = Gtk.RadioButton.new_with_label_from_widget(
            self._radio_image, _("Texte"))
        self._radio_image.connect("toggled", lambda *_a: self._update_sensitivity())
        type_grid.attach(self._radio_image, 0, 0, 1, 1)
        type_grid.attach(self._radio_text, 1, 0, 1, 1)
        page.pack_start(type_frame, False, False, 0)

        # --- Filigrane image ---
        img_frame, img_grid = self._make_frame(_("Filigrane image"))
        self._logo_chooser = Gtk.FileChooserButton(
            title=_("Choisir un logo PNG"), action=Gtk.FileChooserAction.OPEN)
        png_filter = Gtk.FileFilter()
        png_filter.set_name(_("Images PNG"))
        png_filter.add_pattern("*.png")
        self._logo_chooser.add_filter(png_filter)
        self._attach_row(img_grid, 0, _("Fichier PNG :"), self._logo_chooser)
        self._image_frame = img_frame
        page.pack_start(img_frame, False, False, 0)

        # --- Filigrane texte ---
        txt_frame, txt_grid = self._make_frame(_("Filigrane texte"))
        self._text_entry = Gtk.Entry()
        self._attach_row(txt_grid, 0, _("Texte :"), self._text_entry)
        self._font_button = Gtk.FontButton()
        self._font_button.set_show_size(False)
        self._attach_row(txt_grid, 1, _("Police :"), self._font_button)
        self._text_size_spin = Gtk.SpinButton.new_with_range(4, 2000, 1)
        self._attach_row(txt_grid, 2, _("Taille police (px) :"), self._text_size_spin)
        self._text_color_button = Gtk.ColorButton()
        self._attach_row(txt_grid, 3, _("Couleur :"), self._text_color_button)

        self._outline_check = Gtk.CheckButton(label=_("Contour"))
        self._outline_check.connect("toggled", lambda *_a: self._update_sensitivity())
        txt_grid.attach(self._outline_check, 0, 4, 1, 1)
        self._outline_color_button = Gtk.ColorButton()
        txt_grid.attach(self._outline_color_button, 1, 4, 1, 1)
        self._outline_width_spin = Gtk.SpinButton.new_with_range(1, 50, 1)
        self._attach_row(txt_grid, 5, _("Épaisseur contour (px) :"), self._outline_width_spin)

        self._shadow_check = Gtk.CheckButton(label=_("Ombre portée"))
        self._shadow_check.connect("toggled", lambda *_a: self._update_sensitivity())
        txt_grid.attach(self._shadow_check, 0, 6, 1, 1)
        self._shadow_color_button = Gtk.ColorButton()
        txt_grid.attach(self._shadow_color_button, 1, 6, 1, 1)
        self._shadow_offset_spin = Gtk.SpinButton.new_with_range(1, 100, 1)
        self._attach_row(txt_grid, 7, _("Décalage ombre (px) :"), self._shadow_offset_spin)
        self._text_frame = txt_frame
        page.pack_start(txt_frame, False, False, 0)

        return self._wrap_scroll(page)

    # -- Onglet Export ----------------------------------------------------
    def _build_export_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.set_border_width(8)

        # --- Apparence (opacité, taille, rotation, position, marges) ---
        look_frame, look_grid = self._make_frame(_("Apparence du filigrane"))

        self._opacity_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self._opacity_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self._opacity_scale.set_hexpand(True)
        self._attach_row(look_grid, 0, _("Opacité (%) :"), self._opacity_scale)

        self._size_mode_combo = self._make_combo({
            m.value: C.SIZE_MODE_LABELS[m] for m in SizeMode})
        self._attach_row(look_grid, 1, _("Mode de taille :"), self._size_mode_combo)
        self._size_value_spin = Gtk.SpinButton.new_with_range(1, 100000, 1)
        self._attach_row(look_grid, 2, _("Valeur de taille :"), self._size_value_spin)

        self._rotation_spin = Gtk.SpinButton.new_with_range(
            C.ROTATION_MIN, C.ROTATION_MAX, 1)
        self._attach_row(look_grid, 3, _("Rotation (°) :"), self._rotation_spin)

        self._position_combo = self._make_combo({
            p.value if p.value is not None else "custom":
            C.POSITION_LABELS[p] for p in Position})
        self._position_combo.connect("changed", lambda *_a: self._update_sensitivity())
        self._attach_row(look_grid, 4, _("Position :"), self._position_combo)

        self._custom_x_spin = Gtk.SpinButton.new_with_range(-100000, 100000, 1)
        self._custom_y_spin = Gtk.SpinButton.new_with_range(-100000, 100000, 1)
        xy_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        xy_box.pack_start(Gtk.Label(label="X"), False, False, 0)
        xy_box.pack_start(self._custom_x_spin, True, True, 0)
        xy_box.pack_start(Gtk.Label(label="Y"), False, False, 0)
        xy_box.pack_start(self._custom_y_spin, True, True, 0)
        self._attach_row(look_grid, 5, _("Coordonnées perso :"), xy_box)

        self._margin_spin = Gtk.SpinButton.new_with_range(0, 100000, 1)
        self._margin_percent_check = Gtk.CheckButton(label=_("en %"))
        margin_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        margin_box.pack_start(self._margin_spin, True, True, 0)
        margin_box.pack_start(self._margin_percent_check, False, False, 0)
        self._attach_row(look_grid, 6, _("Marge :"), margin_box)
        page.pack_start(look_frame, False, False, 0)

        # --- Format & qualité ---
        fmt_frame, fmt_grid = self._make_frame(_("Format de sortie"))
        self._format_combo = self._make_combo({
            f.value: C.FORMAT_LABELS[f] for f in ExportFormat})
        self._attach_row(fmt_grid, 0, _("Format :"), self._format_combo)
        self._quality_spin = Gtk.SpinButton.new_with_range(0, 100, 1)
        self._attach_row(fmt_grid, 1, _("Qualité JPEG/WebP (%) :"), self._quality_spin)
        self._compression_spin = Gtk.SpinButton.new_with_range(0, 9, 1)
        self._attach_row(fmt_grid, 2, _("Compression PNG (0-9) :"), self._compression_spin)
        page.pack_start(fmt_frame, False, False, 0)

        # --- Destination ---
        dest_frame, dest_grid = self._make_frame(_("Dossier de sortie"))
        self._output_chooser = Gtk.FileChooserButton(
            title=_("Dossier de sortie"), action=Gtk.FileChooserAction.SELECT_FOLDER)
        self._attach_row(dest_grid, 0, _("Dossier :"), self._output_chooser)
        self._source_folder_check = Gtk.CheckButton(
            label=_("Exporter à côté de chaque image d'origine"))
        self._source_folder_check.connect("toggled", lambda *_a: self._update_sensitivity())
        dest_grid.attach(self._source_folder_check, 0, 1, 2, 1)
        self._subfolder_check = Gtk.CheckButton(
            label=_("Créer un sous-dossier « exports »"))
        dest_grid.attach(self._subfolder_check, 0, 2, 2, 1)
        page.pack_start(dest_frame, False, False, 0)

        # --- Nommage ---
        name_frame, name_grid = self._make_frame(_("Nommage des fichiers"))
        self._naming_combo = self._make_combo({
            m.value: C.NAMING_MODE_LABELS[m] for m in NamingMode})
        self._naming_combo.connect("changed", lambda *_a: self._update_sensitivity())
        self._attach_row(name_grid, 0, _("Mode :"), self._naming_combo)
        self._prefix_entry = Gtk.Entry()
        self._attach_row(name_grid, 1, _("Préfixe :"), self._prefix_entry)
        self._suffix_entry = Gtk.Entry()
        self._attach_row(name_grid, 2, _("Suffixe :"), self._suffix_entry)
        self._pattern_entry = Gtk.Entry()
        self._pattern_entry.set_tooltip_text(
            _("Variables : {filename} {date} {width} {height} {prefix} {suffix}"))
        self._attach_row(name_grid, 3, _("Motif perso :"), self._pattern_entry)
        self._overwrite_check = Gtk.CheckButton(label=_("Écraser les fichiers existants"))
        name_grid.attach(self._overwrite_check, 0, 4, 2, 1)
        page.pack_start(name_frame, False, False, 0)

        # --- Options de traitement ---
        opt_frame, opt_grid = self._make_frame(_("Options"))
        self._skip_check = Gtk.CheckButton(label=_("Ignorer les images non modifiées"))
        opt_grid.attach(self._skip_check, 0, 0, 2, 1)
        self._debug_check = Gtk.CheckButton(label=_("Activer le mode debug (journalisation détaillée)"))
        opt_grid.attach(self._debug_check, 0, 1, 2, 1)
        page.pack_start(opt_frame, False, False, 0)

        # --- Charge machine ---
        load_frame, load_grid = self._make_frame(_("Charge machine"))
        self._limit_cpu_check = Gtk.CheckButton(
            label=_("Brider le traitement (laisser des cœurs libres)"))
        self._limit_cpu_check.set_tooltip_text(
            _("Réduit le nombre de threads utilisés par le moteur de GIMP "
              "pendant l'export : le poste reste utilisable, au prix d'un "
              "export un peu plus long."))
        self._limit_cpu_check.connect("toggled", lambda *_a: self._update_sensitivity())
        load_grid.attach(self._limit_cpu_check, 0, 0, 2, 1)

        self._cpu_reserve_spin = Gtk.SpinButton.new_with_range(0, C.CPU_RESERVE_MAX, 1)
        self._attach_row(load_grid, 1, _("Cœurs laissés libres :"), self._cpu_reserve_spin)

        self._throttle_spin = Gtk.SpinButton.new_with_range(0, C.THROTTLE_MS_MAX, 10)
        self._throttle_spin.set_tooltip_text(
            _("Temps rendu au système entre deux images. Augmentez cette valeur "
              "si la machine reste trop chargée pendant les gros lots."))
        self._attach_row(load_grid, 2, _("Pause entre images (ms) :"), self._throttle_spin)
        page.pack_start(load_frame, False, False, 0)

        return self._wrap_scroll(page)

    # ------------------------------------------------------------------ #
    # Fabriques de widgets réutilisables
    # ------------------------------------------------------------------ #
    @staticmethod
    def _make_frame(title: str) -> tuple[Gtk.Frame, Gtk.Grid]:
        """Crée un cadre titré contenant une grille prête à l'emploi."""
        frame = Gtk.Frame(label=title)
        frame.set_label_align(0.02, 0.5)
        grid = Gtk.Grid()
        grid.set_row_spacing(6)
        grid.set_column_spacing(10)
        grid.set_border_width(8)
        grid.set_column_homogeneous(False)
        frame.add(grid)
        return frame, grid

    @staticmethod
    def _attach_row(grid: Gtk.Grid, row: int, label: str, widget: Gtk.Widget) -> None:
        """Ajoute une ligne « libellé : widget » à une grille."""
        lbl = Gtk.Label(label=label)
        lbl.set_xalign(0.0)
        widget.set_hexpand(True)
        grid.attach(lbl, 0, row, 1, 1)
        grid.attach(widget, 1, row, 1, 1)

    @staticmethod
    def _make_combo(items: dict) -> Gtk.ComboBoxText:
        """Crée une liste déroulante à partir d'un dict ``{id: libellé}``."""
        combo = Gtk.ComboBoxText()
        for item_id, label in items.items():
            combo.append(str(item_id), label)
        return combo

    @staticmethod
    def _wrap_scroll(widget: Gtk.Widget) -> Gtk.ScrolledWindow:
        """Enveloppe un widget dans une zone défilable verticale."""
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.add(widget)
        return scroller

    # ------------------------------------------------------------------ #
    # Synchronisation Settings <-> widgets
    # ------------------------------------------------------------------ #
    def _load_settings_into_widgets(self) -> None:
        """Recopie les préférences vers les widgets de l'interface."""
        s = self._settings
        self._radio_image.set_active(s.watermark_type is WatermarkType.IMAGE)
        self._radio_text.set_active(s.watermark_type is WatermarkType.TEXT)
        if s.watermark_path:
            self._logo_chooser.set_filename(s.watermark_path)

        self._text_entry.set_text(s.watermark_text)
        self._font_button.set_font(s.text_font)
        self._text_size_spin.set_value(s.text_size)
        self._text_color_button.set_rgba(_rgba_from_hex(s.text_color))
        self._outline_check.set_active(s.text_outline)
        self._outline_color_button.set_rgba(_rgba_from_hex(s.text_outline_color))
        self._outline_width_spin.set_value(s.text_outline_width)
        self._shadow_check.set_active(s.text_shadow)
        self._shadow_color_button.set_rgba(_rgba_from_hex(s.text_shadow_color))
        self._shadow_offset_spin.set_value(s.text_shadow_offset)

        self._opacity_scale.set_value(s.opacity)
        self._size_mode_combo.set_active_id(s.size_mode.value)
        self._size_value_spin.set_value(s.size_value)
        self._rotation_spin.set_value(s.rotation)
        self._position_combo.set_active_id(
            str(s.position.value) if s.position.value is not None else "custom")
        self._custom_x_spin.set_value(s.custom_x)
        self._custom_y_spin.set_value(s.custom_y)
        self._margin_spin.set_value(s.margin_value)
        self._margin_percent_check.set_active(s.margin_is_percent)

        self._format_combo.set_active_id(s.export_format.value)
        self._quality_spin.set_value(s.jpeg_quality)
        self._compression_spin.set_value(s.png_compression)
        if s.output_dir:
            self._output_chooser.set_current_folder(s.output_dir)
        self._source_folder_check.set_active(s.use_source_folder)
        self._subfolder_check.set_active(s.create_subfolder)

        self._naming_combo.set_active_id(s.naming_mode.value)
        self._prefix_entry.set_text(s.prefix)
        self._suffix_entry.set_text(s.suffix)
        self._pattern_entry.set_text(s.custom_pattern)
        self._overwrite_check.set_active(s.overwrite)
        self._skip_check.set_active(s.skip_unmodified)
        self._debug_check.set_active(s.debug)
        self._limit_cpu_check.set_active(s.limit_cpu)
        self._cpu_reserve_spin.set_value(s.cpu_reserve)
        self._throttle_spin.set_value(s.throttle_ms)

    def _read_widgets_into_settings(self) -> None:
        """Recopie les valeurs des widgets vers les préférences."""
        s = self._settings
        s.watermark_type = (WatermarkType.IMAGE if self._radio_image.get_active()
                            else WatermarkType.TEXT)
        s.watermark_path = self._logo_chooser.get_filename() or ""

        s.watermark_text = self._text_entry.get_text()
        s.text_font = self._parse_font(self._font_button.get_font())
        s.text_size = self._text_size_spin.get_value()
        s.text_color = _hex_from_rgba(self._text_color_button.get_rgba())
        s.text_outline = self._outline_check.get_active()
        s.text_outline_color = _hex_from_rgba(self._outline_color_button.get_rgba())
        s.text_outline_width = self._outline_width_spin.get_value_as_int()
        s.text_shadow = self._shadow_check.get_active()
        s.text_shadow_color = _hex_from_rgba(self._shadow_color_button.get_rgba())
        s.text_shadow_offset = self._shadow_offset_spin.get_value_as_int()

        s.opacity = self._opacity_scale.get_value()
        s.size_mode = SizeMode(self._size_mode_combo.get_active_id())
        s.size_value = self._size_value_spin.get_value()
        s.rotation = self._rotation_spin.get_value()
        pos_id = self._position_combo.get_active_id()
        s.position = Position.CUSTOM if pos_id == "custom" else Position(_parse_pos(pos_id))
        s.custom_x = self._custom_x_spin.get_value_as_int()
        s.custom_y = self._custom_y_spin.get_value_as_int()
        s.margin_value = self._margin_spin.get_value()
        s.margin_is_percent = self._margin_percent_check.get_active()

        s.export_format = ExportFormat(self._format_combo.get_active_id())
        s.jpeg_quality = self._quality_spin.get_value_as_int()
        s.png_compression = self._compression_spin.get_value_as_int()
        s.output_dir = self._output_chooser.get_filename() or ""
        s.use_source_folder = self._source_folder_check.get_active()
        s.create_subfolder = self._subfolder_check.get_active()

        s.naming_mode = NamingMode(self._naming_combo.get_active_id())
        s.prefix = self._prefix_entry.get_text()
        s.suffix = self._suffix_entry.get_text()
        s.custom_pattern = self._pattern_entry.get_text()
        s.overwrite = self._overwrite_check.get_active()
        s.skip_unmodified = self._skip_check.get_active()
        s.debug = self._debug_check.get_active()
        s.limit_cpu = self._limit_cpu_check.get_active()
        s.cpu_reserve = self._cpu_reserve_spin.get_value_as_int()
        s.throttle_ms = self._throttle_spin.get_value_as_int()

    @staticmethod
    def _parse_font(font_string: Optional[str]) -> str:
        """Extrait un nom de police GIMP d'une chaîne GtkFontButton.

        GtkFontButton peut renvoyer une taille finale (« Sans Bold 12 ») ; on
        retire un éventuel nombre terminal pour obtenir « Sans Bold ».
        """
        if not font_string:
            return "Sans-serif"
        parts = font_string.rsplit(" ", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return parts[0]
        return font_string

    # ------------------------------------------------------------------ #
    # Sensibilité dynamique des sections
    # ------------------------------------------------------------------ #
    def _update_sensitivity(self) -> None:
        """Active/désactive les sections selon les choix courants."""
        is_image = self._radio_image.get_active()
        self._image_frame.set_sensitive(is_image)
        self._text_frame.set_sensitive(not is_image)

        self._outline_color_button.set_sensitive(self._outline_check.get_active())
        self._outline_width_spin.set_sensitive(self._outline_check.get_active())
        self._shadow_color_button.set_sensitive(self._shadow_check.get_active())
        self._shadow_offset_spin.set_sensitive(self._shadow_check.get_active())

        is_custom_pos = self._position_combo.get_active_id() == "custom"
        self._custom_x_spin.set_sensitive(is_custom_pos)
        self._custom_y_spin.set_sensitive(is_custom_pos)

        use_source = self._source_folder_check.get_active()
        self._output_chooser.set_sensitive(not use_source)

        is_custom_name = self._naming_combo.get_active_id() == NamingMode.CUSTOM.value
        self._pattern_entry.set_sensitive(is_custom_name)

        self._cpu_reserve_spin.set_sensitive(self._limit_cpu_check.get_active())

    # ------------------------------------------------------------------ #
    # Boucle d'exécution
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        """Affiche la fenêtre et bloque jusqu'à sa fermeture."""
        self.dialog.connect("response", self._on_response)
        self.dialog.connect("delete-event", self._on_delete_event)
        self.dialog.connect("destroy", self._on_destroy)
        self.dialog.show_all()
        self._update_sensitivity()
        Gtk.main()

    def _on_response(self, _dialog: Gtk.Dialog, response: int) -> None:
        """Gère les clics sur les boutons de la fenêtre."""
        if response == Gtk.ResponseType.OK:
            if not self._running:
                self._on_export_clicked()
        elif self._running:
            # Pendant un export, « Annuler » interrompt le lot au lieu de fermer
            # la fenêtre : l'image en cours va jusqu'au bout, les suivantes sont
            # abandonnées, et le résumé est affiché normalement.
            self._request_cancel()
        else:
            self.dialog.destroy()

    def _on_delete_event(self, *_args) -> bool:
        """Empêche la fermeture pendant un export (demande l'annulation à la place)."""
        if self._running:
            self._request_cancel()
            return True  # Consomme l'événement : la fenêtre reste ouverte.
        return False

    def _on_destroy(self, *_args) -> None:
        """Libère l'export en cours puis quitte la boucle GTK."""
        self._stop_export()
        Gtk.main_quit()

    def _request_cancel(self) -> None:
        """Marque le lot comme annulé (prise en compte après l'image en cours)."""
        if self._cancel_requested:
            return
        self._cancel_requested = True
        _log.info("Annulation de l'export demandée par l'utilisateur.")
        self._progress_bar.set_text(_("Annulation en cours…"))
        self._append_log(_("Annulation demandée — fin de l'image en cours…"))

    def _on_export_clicked(self) -> None:
        """Valide, persiste puis démarre l'export piloté par la boucle GTK."""
        self._read_widgets_into_settings()

        errors = utils.validate_export_parameters(
            watermark_type=self._settings.watermark_type,
            watermark_path=self._settings.watermark_path,
            watermark_text=self._settings.watermark_text,
            opacity=self._settings.opacity,
            size_value=self._settings.size_value,
            margin_value=self._settings.margin_value,
            output_dir=self._settings.output_dir,
            use_source_folder=self._settings.use_source_folder,
            export_format=self._settings.export_format,
        )
        if errors:
            self._show_message(Gtk.MessageType.WARNING,
                               _("Paramètres invalides"), "\n".join(errors))
            return

        self._manager.save(self._settings)

        self._running = True
        self._cancel_requested = False
        self._results = []
        self._export_button.set_sensitive(False)
        self._log_buffer.set_text("")
        self._progress_bar.set_fraction(0.0)
        self._progress_bar.set_text(_("Préparation…"))

        try:
            self._export_iter = iter(self._export_runner(
                self._settings, self._on_progress, self._on_stage))
        except Exception as exc:  # noqa: BLE001 - l'UI ne doit jamais planter.
            _log.exception("Erreur inattendue au démarrage de l'export")
            self._show_message(Gtk.MessageType.ERROR, _("Erreur"), str(exc))
            # Pas de résumé : l'erreur vient d'être affichée, rien n'a été traité.
            self._finish_export(summary=False)
            return

        self._schedule_next_step()

    # -- Pilotage pas à pas depuis la boucle GTK --------------------------
    def _schedule_next_step(self) -> None:
        """Programme le traitement de l'image suivante dans la boucle GTK.

        La pause configurée (``throttle_ms``) sert à deux choses : rendre la
        main à GTK — donc au gestionnaire de fenêtres — et laisser respirer le
        système entre deux images d'un gros lot.
        """
        delay = max(0, self._settings.throttle_ms)
        self._step_source = GLib.timeout_add(delay, self._export_step)

    def _export_step(self) -> bool:
        """Traite **une** image puis reprogramme la suivante.

        :return: toujours ``False`` — chaque source GTK ne s'exécute qu'une
            fois, la suivante étant réarmée explicitement.
        """
        self._step_source = 0

        if self._cancel_requested:
            self._finish_export(cancelled=True)
            return False

        try:
            result = next(self._export_iter)  # type: ignore[arg-type]
        except StopIteration:
            self._finish_export()
            return False
        except Exception as exc:  # noqa: BLE001 - l'UI ne doit jamais planter.
            _log.exception("Erreur inattendue pendant l'export")
            self._show_message(Gtk.MessageType.ERROR, _("Erreur"), str(exc))
            self._finish_export()
            return False

        self._results.append(result)
        self._schedule_next_step()
        return False

    def _stop_export(self) -> None:
        """Arrête l'itérateur d'export et désarme la source GTK en attente."""
        if self._step_source:
            GLib.source_remove(self._step_source)
            self._step_source = 0
        if self._export_iter is not None:
            close = getattr(self._export_iter, "close", None)
            if callable(close):
                # Referme le générateur : ses blocs ``finally`` s'exécutent
                # (fin de la barre GIMP, restauration de la charge GEGL).
                close()
            self._export_iter = None

    def _finish_export(self, cancelled: bool = False, summary: bool = True) -> None:
        """Clôture l'export : nettoyage, réactivation des boutons, résumé."""
        self._stop_export()
        self._running = False
        self._cancel_requested = False
        self._export_button.set_sensitive(True)
        if summary:
            self._show_summary(self._results, cancelled=cancelled)

    # -- Rappels du moteur d'export ---------------------------------------
    def _on_progress(self, index: int, total: int, name: str, status: str) -> None:
        """Rappel de progression : met à jour la barre et le journal."""
        fraction = index / total if total else 1.0
        self._progress_bar.set_fraction(fraction)
        self._progress_bar.set_text(f"{index}/{total} — {name}")
        self._append_log(f"[{status}] {name}")

    def _on_stage(self, label: str) -> None:
        """Rappel d'étape : pompe la file d'événements au milieu d'une image.

        Sans cela, une image lourde bloquerait la boucle GTK de bout en bout et
        le gestionnaire de fenêtres déclarerait la fenêtre « ne répond pas ».
        """
        total = self._image_count
        current = min(len(self._results) + 1, total) if total else 0
        self._progress_bar.set_text(f"{current}/{total} — {label}")
        while Gtk.events_pending():
            Gtk.main_iteration()

    # ------------------------------------------------------------------ #
    # Retours utilisateur
    # ------------------------------------------------------------------ #
    def _append_log(self, line: str) -> None:
        """Ajoute une ligne au journal visible et fait défiler vers le bas."""
        end = self._log_buffer.get_end_iter()
        self._log_buffer.insert(end, line + "\n")

    def _show_summary(self, results: List, cancelled: bool = False) -> None:
        """Affiche un résumé de fin d'export.

        :param results: résultats des images effectivement traitées.
        :param cancelled: ``True`` si l'utilisateur a interrompu le lot.
        """
        total = len(results)
        failed = [r for r in results if not r.success]
        succeeded = total - len(failed)

        if cancelled:
            self._progress_bar.set_text(_("Annulé"))
        else:
            self._progress_bar.set_fraction(1.0)
            self._progress_bar.set_text(_("Terminé"))

        if not total:
            message = (_("Export annulé : aucune image traitée.") if cancelled
                       else _("Aucune image à traiter."))
            self._show_message(Gtk.MessageType.INFO, _("Export"), message)
            return

        lines = [f"{succeeded}/{total} image(s) exportée(s) avec succès."]
        if cancelled:
            remaining = max(0, self._image_count - total)
            lines.append(_("Export interrompu — {n} image(s) non traitée(s).")
                         .format(n=remaining))
        if failed:
            lines.append("")
            lines.append(_("Échecs :"))
            for res in failed:
                lines.append(f"  • {res.image_name} : {res.error_message}")

        msg_type = Gtk.MessageType.INFO if not failed else Gtk.MessageType.WARNING
        title = _("Export annulé") if cancelled else _("Export terminé")
        self._show_message(msg_type, title, "\n".join(lines))

    def _show_message(self, msg_type: Gtk.MessageType, title: str, body: str) -> None:
        """Affiche une boîte de dialogue modale d'information/erreur."""
        dialog = Gtk.MessageDialog(
            transient_for=self.dialog, modal=True,
            message_type=msg_type, buttons=Gtk.ButtonsType.OK, text=title)
        dialog.format_secondary_text(body)
        dialog.run()
        dialog.destroy()


def _parse_pos(pos_id: str) -> tuple:
    """Reconvertit l'identifiant d'une position (« (2, 2) ») en tuple d'ancres."""
    for position in Position:
        if position.value is not None and str(position.value) == pos_id:
            return position.value
    return (1, 1)
