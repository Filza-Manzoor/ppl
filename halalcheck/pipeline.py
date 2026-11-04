"""Glue between data sources and the rule engine. No network and no UI here."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import rules
from .off import Product
from .vision import DishReading, LabelReading

RECIPE_NOTE = (
    "Recipes differ between countries and change over time. "
    "Check the ingredient list on the pack in your hand."
)


@dataclass
class Result:
    analysis: rules.Analysis
    source: str  # "barcode", "name", "label" or "dish"
    title: str = ""
    warnings: list[str] = field(default_factory=list)


def check_product(product: Product, country_tag: str | None = None, source: str = "barcode") -> Result:
    claim = rules.detect_halal_claim(product.labels_tags, product.ingredients_text)
    analysis = rules.analyze(
        product.ingredients_text,
        tags=() if product.ingredients_text.strip() else product.ingredients_tags,
        additives=product.additives_tags,
        halal_claim=claim,
    )
    title = " - ".join(p for p in (product.name, product.brands) if p) or product.code
    warnings = [RECIPE_NOTE]
    if country_tag and product.countries and not product.sold_in(country_tag):
        warnings.insert(
            0,
            "This record is for a version sold in "
            + ", ".join(c.replace("-", " ").title() for c in product.countries[:3])
            + ", not your selected country. The recipe there may differ.",
        )
    if source == "name":
        warnings.append("This came from a name search. Scan the ingredient list to be sure it is the same product.")
    if not product.has_ingredients:
        warnings.append("This product has no ingredient list in the database. Photograph the ingredient list instead.")
    return Result(analysis=analysis, source=source, title=title, warnings=warnings)


def check_label(reading: LabelReading) -> Result:
    if not reading.readable:
        analysis = rules.analyze("")
        return Result(
            analysis=analysis,
            source="label",
            title=reading.product_name,
            warnings=["The ingredient list was not readable. Try better light and hold the camera steady."],
        )
    analysis = rules.analyze(reading.ingredients_text, halal_claim=reading.halal_logo_seen)
    warnings = ["The text was read from your photo by an AI. Compare it with the pack if the result matters."]
    if reading.halal_logo_seen:
        warnings.append("A halal mark was seen on the pack. Check who issues it.")
    return Result(analysis=analysis, source="label", title=reading.product_name, warnings=warnings)


def check_dish(reading: DishReading) -> Result:
    if not reading.is_food or not reading.ingredients:
        return Result(
            analysis=rules.analyze(""),
            source="dish",
            title=reading.dish_name,
            warnings=["This does not look like a food photo, or the dish could not be recognised."],
        )
    analysis = rules.analyze(", ".join(reading.ingredients), mode="dish")
    return Result(
        analysis=analysis,
        source="dish",
        title=reading.dish_name,
        warnings=["These ingredients are a guess from the photo. They are not facts about this exact dish."],
    )
