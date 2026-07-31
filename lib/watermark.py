#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rendu du filigrane sur une image GIMP.

Ce module encapsule **toute** l'interaction avec l'API GIMP nécessaire à la
construction et à l'application d'un filigrane. Il gère les deux modes :

* **Image** : un logo PNG transparent, redimensionné en conservant son ratio ;
* **Texte** : un filigrane texte généré dynamiquement, avec contour et ombre
  portée optionnels.

Le filigrane est toujours appliqué sur l'image reçue (qui, côté appelant, est
une **copie temporaire** — les originaux ne sont jamais touchés). Le module ne
prend aucune décision de haut niveau (itération sur les images, export…) : sa
seule responsabilité est de poser un calque de filigrane correctement
dimensionné, tourné, positionné et opacifié (responsabilité unique).
"""

from __future__ import annotations

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("Gegl", "0.4")
from gi.repository import Gegl, Gimp, Gio  # noqa: E402

from . import utils  # noqa: E402
from .constants import Position, WatermarkType  # noqa: E402
from .logger import get_logger  # noqa: E402
from .settings import Settings  # noqa: E402

_log = get_logger("watermark")


class WatermarkError(Exception):
    """Erreur survenue pendant la construction/application du filigrane."""


# ---------------------------------------------------------------------------
# Helpers couleur
# ---------------------------------------------------------------------------

def hex_to_gegl_color(hex_color: str, alpha: float = 1.0) -> Gegl.Color:
    """Convertit une couleur hexadécimale ``#rrggbb`` en :class:`Gegl.Color`.

    :param hex_color: couleur au format ``#rrggbb`` ou ``rrggbb``.
    :param alpha: composante alpha (0.0 à 1.0).
    :return: un objet :class:`Gegl.Color`.

    Une valeur invalide retombe silencieusement sur du noir opaque : le rendu
    ne doit jamais échouer à cause d'une couleur mal saisie.
    """
    color = Gegl.Color.new("black")
    text = (hex_color or "").strip().lstrip("#")
    try:
        if len(text) == 3:  # forme courte #rgb
            text = "".join(ch * 2 for ch in text)
        red = int(text[0:2], 16) / 255.0
        green = int(text[2:4], 16) / 255.0
        blue = int(text[4:6], 16) / 255.0
    except (ValueError, IndexError):
        red = green = blue = 0.0
    color.set_rgba(red, green, blue, utils.clamp(alpha, 0.0, 1.0))
    return color


# ---------------------------------------------------------------------------
# Renderer principal
# ---------------------------------------------------------------------------

class WatermarkRenderer:
    """Construit et applique un filigrane sur une image GIMP.

    Instancier puis appeler :meth:`apply`. L'objet est sans état entre deux
    appels : il peut être réutilisé pour toutes les images d'un même lot.
    """

    def apply(self, image: Gimp.Image, settings: Settings) -> Gimp.Layer:
        """Applique le filigrane décrit par ``settings`` sur ``image``.

        :param image: l'image (copie temporaire) à filigraner.
        :param settings: préférences décrivant le filigrane.
        :return: le calque de filigrane inséré (déjà dimensionné/positionné).
        :raises WatermarkError: en cas d'échec de construction du filigrane.
        """
        base_width = image.get_width()
        base_height = image.get_height()

        if settings.watermark_type is WatermarkType.IMAGE:
            layer = self._build_image_layer(image, settings)
        else:
            layer = self._build_text_layer(image, settings)

        if layer is None:  # pragma: no cover - garde-fou.
            raise WatermarkError("La construction du calque de filigrane a échoué.")

        self._transform_layer(image, layer, settings, base_width, base_height)
        return layer

    # ------------------------------------------------------------------ #
    # Mode IMAGE (logo PNG)
    # ------------------------------------------------------------------ #
    def _build_image_layer(self, image: Gimp.Image, settings: Settings) -> Gimp.Layer:
        """Charge le logo PNG et l'insère au sommet de la pile de calques."""
        path = settings.watermark_path
        gio_file = Gio.File.new_for_path(path)
        try:
            layer = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, image, gio_file)
        except Exception as exc:  # noqa: BLE001 - on remonte une erreur claire.
            raise WatermarkError(f"Impossible de charger le logo « {path} » : {exc}") from exc

        if layer is None:
            raise WatermarkError(f"Le logo « {path} » n'a pas pu être chargé.")

        image.insert_layer(layer, None, 0)
        if not layer.has_alpha():
            layer.add_alpha()
        layer.set_name("Filigrane (image)")
        _log.debug("Logo chargé : %dx%d px", layer.get_width(), layer.get_height())
        return layer

    # ------------------------------------------------------------------ #
    # Mode TEXTE
    # ------------------------------------------------------------------ #
    def _build_text_layer(self, image: Gimp.Image, settings: Settings) -> Gimp.Layer:
        """Construit un filigrane texte (avec contour/ombre) et le copie dans ``image``.

        Le texte est d'abord assemblé dans une **image temporaire (scratch)**
        isolée : cela permet de fusionner texte + contour + ombre en un unique
        calque RGBA sans jamais fusionner avec le contenu de l'image cible.
        """
        scratch = None
        try:
            scratch = Gimp.Image.new(1, 1, Gimp.ImageBaseType.RGB)

            font = self._resolve_font(settings.text_font)
            text_layer = Gimp.TextLayer.new(
                scratch, settings.watermark_text, font,
                settings.text_size, Gimp.Unit.pixel(),
            )
            scratch.insert_layer(text_layer, None, 0)
            text_layer.set_color(hex_to_gegl_color(settings.text_color))
            text_layer.set_antialias(True)

            text_w = text_layer.get_width()
            text_h = text_layer.get_height()

            # Marge interne pour accueillir contour, décalage et flou d'ombre.
            outline = settings.text_outline_width if settings.text_outline else 0
            shadow_off = settings.text_shadow_offset if settings.text_shadow else 0
            pad = outline + shadow_off + 8
            canvas_w = text_w + 2 * pad
            canvas_h = text_h + 2 * pad

            # Agrandit le canevas et recentre le texte (offset = pad, pad).
            scratch.resize(canvas_w, canvas_h, pad, pad)

            # Ordre d'empilement (du bas vers le haut) : ombre, contour, texte.
            if settings.text_shadow:
                self._add_shadow(scratch, text_layer, settings, canvas_w, canvas_h)
            if settings.text_outline:
                self._add_outline(scratch, text_layer, settings, canvas_w, canvas_h)

            Gimp.Selection.none(scratch)
            merged = scratch.merge_visible_layers(Gimp.MergeType.CLIP_TO_IMAGE)

            # Copie du calque fusionné vers l'image cible.
            layer = Gimp.Layer.new_from_drawable(merged, image)
            image.insert_layer(layer, None, 0)
            if not layer.has_alpha():
                layer.add_alpha()
            layer.set_name("Filigrane (texte)")
            _log.debug("Filigrane texte construit : %dx%d px",
                       layer.get_width(), layer.get_height())
            return layer
        except WatermarkError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise WatermarkError(f"Échec de la construction du filigrane texte : {exc}") from exc
        finally:
            if scratch is not None:
                scratch.delete()

    @staticmethod
    def _resolve_font(name: str) -> Gimp.Font:
        """Retourne une police GIMP valide, avec repli sur la police courante.

        :param name: nom de police souhaité (ex. ``"Sans-serif Bold"``).
        :return: une :class:`Gimp.Font` toujours valide.

        Si le nom demandé est introuvable dans la liste des polices de GIMP, on
        se rabat sur la police du contexte courant : la génération du texte ne
        doit jamais échouer à cause d'un nom de police inconnu.
        """
        font = Gimp.Font.get_by_name(name) if name else None
        if font is None:
            _log.debug("Police « %s » introuvable — police courante utilisée.", name)
            font = Gimp.context_get_font()
        return font

    def _add_shadow(self, scratch: Gimp.Image, text_layer: Gimp.Layer,
                    settings: Settings, canvas_w: int, canvas_h: int) -> None:
        """Ajoute une ombre portée floutée sous le texte."""
        shadow = Gimp.Layer.new(
            scratch, "ombre", canvas_w, canvas_h,
            Gimp.ImageType.RGBA_IMAGE, 100.0, Gimp.LayerMode.NORMAL,
        )
        scratch.insert_layer(shadow, None, 1)  # juste sous le texte
        shadow.fill(Gimp.FillType.TRANSPARENT)

        # Remplit la forme du texte avec la couleur d'ombre.
        scratch.select_item(Gimp.ChannelOps.REPLACE, text_layer)
        Gimp.context_push()
        try:
            Gimp.context_set_foreground(hex_to_gegl_color(settings.text_shadow_color))
            shadow.edit_fill(Gimp.FillType.FOREGROUND)
        finally:
            Gimp.context_pop()
        Gimp.Selection.none(scratch)

        # Décale l'ombre.
        off = settings.text_shadow_offset
        ox, oy = text_layer.get_offsets()[1:]
        shadow.set_offsets(ox + off, oy + off)

        # Flou gaussien (meilleur effort ; l'ombre reste nette en cas d'échec).
        try:
            blur = Gimp.DrawableFilter.new(shadow, "gegl:gaussian-blur", "ombre-flou")
            config = blur.get_config()
            std_dev = max(1.0, float(off))
            config.set_property("std-dev-x", std_dev)
            config.set_property("std-dev-y", std_dev)
            blur.update()
            shadow.merge_filter(blur)
        except Exception as exc:  # noqa: BLE001
            _log.debug("Flou d'ombre indisponible (%s) — ombre nette conservée.", exc)

    def _add_outline(self, scratch: Gimp.Image, text_layer: Gimp.Layer,
                     settings: Settings, canvas_w: int, canvas_h: int) -> None:
        """Ajoute un contour autour du texte (sélection dilatée + remplissage)."""
        outline = Gimp.Layer.new(
            scratch, "contour", canvas_w, canvas_h,
            Gimp.ImageType.RGBA_IMAGE, 100.0, Gimp.LayerMode.NORMAL,
        )
        # Inséré juste sous le texte (au-dessus de l'éventuelle ombre).
        position = 1 if not settings.text_shadow else 1
        scratch.insert_layer(outline, None, position)
        outline.fill(Gimp.FillType.TRANSPARENT)

        scratch.select_item(Gimp.ChannelOps.REPLACE, text_layer)
        Gimp.Selection.grow(scratch, max(1, settings.text_outline_width))
        Gimp.context_push()
        try:
            Gimp.context_set_foreground(hex_to_gegl_color(settings.text_outline_color))
            outline.edit_fill(Gimp.FillType.FOREGROUND)
        finally:
            Gimp.context_pop()
        Gimp.Selection.none(scratch)

    # ------------------------------------------------------------------ #
    # Transformations communes (taille, rotation, opacité, position)
    # ------------------------------------------------------------------ #
    def _transform_layer(self, image: Gimp.Image, layer: Gimp.Layer,
                         settings: Settings, base_width: int, base_height: int) -> None:
        """Applique taille, opacité, rotation puis position au calque filigrane."""
        # 1. Redimensionnement (ratio conservé).
        target_w, target_h = utils.compute_scaled_size(
            base_width, base_height,
            layer.get_width(), layer.get_height(),
            settings.size_mode, settings.size_value,
        )
        layer.scale(target_w, target_h, False)

        # 2. Opacité globale du filigrane.
        layer.set_opacity(utils.clamp(settings.opacity, 0.0, 100.0))

        # 3. Rotation optionnelle (autour du centre du calque).
        if abs(settings.rotation) > 1e-6:
            layer = self._rotate_layer(image, layer, settings.rotation)

        # 4. Positionnement final.
        margin_x, margin_y = utils.resolve_margin(
            settings.margin_value, settings.margin_is_percent,
            base_width, base_height,
        )
        pos_x, pos_y = utils.compute_position(
            settings.position, base_width, base_height,
            layer.get_width(), layer.get_height(),
            margin_x, margin_y,
            settings.custom_x, settings.custom_y,
        )
        layer.set_offsets(pos_x, pos_y)
        _log.debug("Filigrane placé en (%d, %d), taille finale %dx%d",
                   pos_x, pos_y, layer.get_width(), layer.get_height())

    def _rotate_layer(self, image: Gimp.Image, layer: Gimp.Layer,
                      degrees: float) -> Gimp.Layer:
        """Fait pivoter ``layer`` de ``degrees`` degrés, calque agrandi au besoin."""
        import math

        Gimp.Selection.none(image)
        Gimp.context_push()
        try:
            Gimp.context_set_transform_resize(Gimp.TransformResize.ADJUST)
            Gimp.context_set_interpolation(Gimp.InterpolationType.CUBIC)
            result = layer.transform_rotate(math.radians(degrees), True, 0.0, 0.0)
        finally:
            Gimp.context_pop()

        # transform_rotate renvoie l'item transformé (le calque lui-même en
        # l'absence de sélection flottante).
        if isinstance(result, Gimp.Layer):
            return result
        return layer
