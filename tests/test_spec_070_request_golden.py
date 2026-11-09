"""Spec 070 SC-004: translate and edit requests stay byte-for-byte what they were.

Spec 070 gives ``audiobook`` its own system prompt template (FR-004).  The loader
(``load_system_prompt``) and the argument builder (``build_system_prompt_arguments``) are shared
with ``translate`` and ``edit``, so the proof that those two are untouched is a hash of every
rendered prompt and of every argument dict over a matrix of variants, intensities, language
pairs and document-context values.

The hashes below were recorded on the untouched base (commit ``564b391``, before any WP-C edit)
and are literals on purpose: a change to a translate/edit prompt, to the intensity files or to
the arguments handed to the loader changes a hash, and the failing case names the axis.  The
test does not read git, so it can be repeated on any branch.  Changing a hash here is a
statement that translate or edit behaviour was changed deliberately -- not a routine update.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

import docxaicorrector.core.config as config
from docxaicorrector.pipeline.support import build_system_prompt_arguments

_PAIRS = (("en", "ru"), ("auto", "ru"), ("ru", "ru"), ("de", "en"))
_CONTEXTS = ("", "Книга о вымышленном городе Альвине. План: три части. Глоссарий: ратуша -> town hall.")
_INTENSITIES = tuple(sorted(config.EDITORIAL_INTENSITY_VALUES))
_OPERATION_VARIANTS = {
    "translate": ("default", "toc_translate", "literary_polish"),
    "edit": ("default",),
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _matrix():
    for operation, variants in _OPERATION_VARIANTS.items():
        for variant in variants:
            for intensity in _INTENSITIES:
                for source, target in _PAIRS:
                    for context_index, context in enumerate(_CONTEXTS):
                        key = f"{operation}|{variant}|{intensity}|{source}>{target}|ctx{context_index}"
                        yield key, operation, variant, intensity, source, target, context


def compute_prompt_hashes() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for key, operation, variant, intensity, source, target, context in _matrix():
        config.load_system_prompt.cache_clear()
        try:
            rendered = config.load_system_prompt(
                operation=operation,
                source_language=source,
                target_language=target,
                editorial_intensity=intensity,
                prompt_variant=variant,
                document_context_prompt=context,
            )
        except RuntimeError as error:
            hashes[key] = "RuntimeError:" + _sha(str(error))
        else:
            hashes[key] = _sha(rendered)
    config.load_system_prompt.cache_clear()
    return hashes


def compute_argument_hashes() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for key, operation, variant, intensity, source, target, context in _matrix():
        fake_context = SimpleNamespace(
            processing_operation=operation,
            source_language=source,
            target_language=target,
            app_config={"editorial_intensity_default": intensity},
            document_context_prompt=context,
        )
        arguments = build_system_prompt_arguments(context=fake_context, prompt_variant=variant)
        hashes[key] = _sha(json.dumps(arguments, sort_keys=True, ensure_ascii=False))
    return hashes


def _diff(actual: dict[str, str], golden: dict[str, str]) -> list[str]:
    changed = [f"{key}: {golden.get(key)} -> {actual.get(key)}" for key in actual if actual[key] != golden.get(key)]
    changed += [f"{key}: missing from actual" for key in golden if key not in actual]
    return changed


def test_translate_and_edit_system_prompts_are_byte_identical_to_the_recorded_base():
    assert _diff(compute_prompt_hashes(), GOLDEN_PROMPT_HASHES) == []


def test_translate_and_edit_prompt_arguments_are_identical_to_the_recorded_base():
    assert _diff(compute_argument_hashes(), GOLDEN_ARGUMENT_HASHES) == []


def test_golden_matrix_is_not_vacuous():
    """A single changed hash must be reachable: the matrix covers both operations and many distinct prompts."""

    assert len(GOLDEN_PROMPT_HASHES) >= 60
    assert len({value for value in GOLDEN_PROMPT_HASHES.values() if not value.startswith("RuntimeError")}) >= 20
    assert any(key.startswith("edit|") for key in GOLDEN_PROMPT_HASHES)
    assert any(key.startswith("translate|toc_translate") for key in GOLDEN_PROMPT_HASHES)


GOLDEN_PROMPT_HASHES: dict[str, str] = {
    "translate|default|conservative|en>ru|ctx0": "085d5859b08a17c7d774b0f9",
    "translate|default|conservative|en>ru|ctx1": "7cc7a84008709b6a138f7b16",
    "translate|default|conservative|auto>ru|ctx0": "39cd845f5ce9937c36fa98e4",
    "translate|default|conservative|auto>ru|ctx1": "bcc1d266a30a9400f4a5adbb",
    "translate|default|conservative|ru>ru|ctx0": "1a97dc7e09b4aff875d9e07a",
    "translate|default|conservative|ru>ru|ctx1": "46ce7fc5245cf1f72f4fdf30",
    "translate|default|conservative|de>en|ctx0": "99bd41ef5d767d357f69e1ad",
    "translate|default|conservative|de>en|ctx1": "7b7db370eed21bcc8fef2d99",
    "translate|default|literary|en>ru|ctx0": "44f3cdadceddc4711502c030",
    "translate|default|literary|en>ru|ctx1": "13d2899c4e192930bae35cef",
    "translate|default|literary|auto>ru|ctx0": "af5b917fd40afd17a4494206",
    "translate|default|literary|auto>ru|ctx1": "03596828e5c9d24a6b15e97d",
    "translate|default|literary|ru>ru|ctx0": "729a97588ec81ea2f395f5cb",
    "translate|default|literary|ru>ru|ctx1": "cacd6d75324336a8aca8f83a",
    "translate|default|literary|de>en|ctx0": "f46a8d1108c9a3ac6702ebf6",
    "translate|default|literary|de>en|ctx1": "4d27a2bc7207453b0a69ae5b",
    "translate|toc_translate|conservative|en>ru|ctx0": "93939c00bce161719ecea859",
    "translate|toc_translate|conservative|en>ru|ctx1": "a6a363f6b61e35de7ef29c05",
    "translate|toc_translate|conservative|auto>ru|ctx0": "5f6fc1ff72a39ea9c6e47fd0",
    "translate|toc_translate|conservative|auto>ru|ctx1": "75720043cb6483f7bcca005f",
    "translate|toc_translate|conservative|ru>ru|ctx0": "90164331cb9d440a9d7c2f12",
    "translate|toc_translate|conservative|ru>ru|ctx1": "90b674441909b946fa4dd1f8",
    "translate|toc_translate|conservative|de>en|ctx0": "074a4d3703b2595ffb57200c",
    "translate|toc_translate|conservative|de>en|ctx1": "3c22070289c1351b5af22004",
    "translate|toc_translate|literary|en>ru|ctx0": "546387aa435e5e3134f7d99f",
    "translate|toc_translate|literary|en>ru|ctx1": "03cc865d7a1b3546c4d15269",
    "translate|toc_translate|literary|auto>ru|ctx0": "1a3329113baca0a8f025052b",
    "translate|toc_translate|literary|auto>ru|ctx1": "b522d1a7ca722c09dc1cceca",
    "translate|toc_translate|literary|ru>ru|ctx0": "517004587ecf56dd7c83aab9",
    "translate|toc_translate|literary|ru>ru|ctx1": "2ac251f2c244202fb6f42c81",
    "translate|toc_translate|literary|de>en|ctx0": "fc718d6e9ad961fdc996bed4",
    "translate|toc_translate|literary|de>en|ctx1": "1a30004f2f8677ac0014bbe8",
    "translate|literary_polish|conservative|en>ru|ctx0": "b4b64a23f088b01d5d732193",
    "translate|literary_polish|conservative|en>ru|ctx1": "26d1622e8e911ac8b7d91fb1",
    "translate|literary_polish|conservative|auto>ru|ctx0": "b4b64a23f088b01d5d732193",
    "translate|literary_polish|conservative|auto>ru|ctx1": "26d1622e8e911ac8b7d91fb1",
    "translate|literary_polish|conservative|ru>ru|ctx0": "b4b64a23f088b01d5d732193",
    "translate|literary_polish|conservative|ru>ru|ctx1": "26d1622e8e911ac8b7d91fb1",
    "translate|literary_polish|conservative|de>en|ctx0": "3e03a830407a0e2327f6a41c",
    "translate|literary_polish|conservative|de>en|ctx1": "eb0a447e892ebfc32669ec87",
    "translate|literary_polish|literary|en>ru|ctx0": "b4b64a23f088b01d5d732193",
    "translate|literary_polish|literary|en>ru|ctx1": "26d1622e8e911ac8b7d91fb1",
    "translate|literary_polish|literary|auto>ru|ctx0": "b4b64a23f088b01d5d732193",
    "translate|literary_polish|literary|auto>ru|ctx1": "26d1622e8e911ac8b7d91fb1",
    "translate|literary_polish|literary|ru>ru|ctx0": "b4b64a23f088b01d5d732193",
    "translate|literary_polish|literary|ru>ru|ctx1": "26d1622e8e911ac8b7d91fb1",
    "translate|literary_polish|literary|de>en|ctx0": "3e03a830407a0e2327f6a41c",
    "translate|literary_polish|literary|de>en|ctx1": "eb0a447e892ebfc32669ec87",
    "edit|default|conservative|en>ru|ctx0": "0e285a312e7ab918b96ecf8c",
    "edit|default|conservative|en>ru|ctx1": "11330e36ad3809049fc1fde1",
    # RuntimeError hashes below: the TEXT of the error for an unsupported `auto` changed in spec 070 WP-B
    # (it now names only `translate`); it is an error message, not request bytes. Request hashes are unchanged.
    "edit|default|conservative|auto>ru|ctx0": "RuntimeError:dc54a5185dcaa04659b3f4eb",
    "edit|default|conservative|auto>ru|ctx1": "RuntimeError:dc54a5185dcaa04659b3f4eb",
    "edit|default|conservative|ru>ru|ctx0": "0e285a312e7ab918b96ecf8c",
    "edit|default|conservative|ru>ru|ctx1": "11330e36ad3809049fc1fde1",
    "edit|default|conservative|de>en|ctx0": "a82990d67315d061272e1766",
    "edit|default|conservative|de>en|ctx1": "48a93e25034c4857e78302cb",
    "edit|default|literary|en>ru|ctx0": "ff9a5ca3e3850fa2f374c0f2",
    "edit|default|literary|en>ru|ctx1": "c0013dfb941d0fb3fe06c631",
    "edit|default|literary|auto>ru|ctx0": "RuntimeError:dc54a5185dcaa04659b3f4eb",
    "edit|default|literary|auto>ru|ctx1": "RuntimeError:dc54a5185dcaa04659b3f4eb",
    "edit|default|literary|ru>ru|ctx0": "ff9a5ca3e3850fa2f374c0f2",
    "edit|default|literary|ru>ru|ctx1": "c0013dfb941d0fb3fe06c631",
    "edit|default|literary|de>en|ctx0": "b17247d658905efa507c9f18",
    "edit|default|literary|de>en|ctx1": "cb7fb3e41e696c42d51be924",
}
GOLDEN_ARGUMENT_HASHES: dict[str, str] = {
    "translate|default|conservative|en>ru|ctx0": "b516e541a2d9c328f1abd5ee",
    "translate|default|conservative|en>ru|ctx1": "5342edc3b098b7752b486cd7",
    "translate|default|conservative|auto>ru|ctx0": "57cd9aee3fa9989dc2b9a514",
    "translate|default|conservative|auto>ru|ctx1": "0c9bfc251647f3ee8ac6fb62",
    "translate|default|conservative|ru>ru|ctx0": "fbb6928ce6b53bbae4b3b692",
    "translate|default|conservative|ru>ru|ctx1": "f199351fce299aa1d17a8782",
    "translate|default|conservative|de>en|ctx0": "ed54d9e210344a912a7b49f1",
    "translate|default|conservative|de>en|ctx1": "4e49c530066539b63d7778a6",
    "translate|default|literary|en>ru|ctx0": "57904a98bb3e989f1fd4bd80",
    "translate|default|literary|en>ru|ctx1": "10ee3960df131e148c795dcc",
    "translate|default|literary|auto>ru|ctx0": "992a93443127764dc4d23645",
    "translate|default|literary|auto>ru|ctx1": "dbcf9feaac35f3625f971916",
    "translate|default|literary|ru>ru|ctx0": "748baefaf414928a2501789c",
    "translate|default|literary|ru>ru|ctx1": "8cf160e405aaaa5667a9059b",
    "translate|default|literary|de>en|ctx0": "ba00f4159bd425a6fa3847a3",
    "translate|default|literary|de>en|ctx1": "0aa2da0ea44def3091cf121d",
    "translate|toc_translate|conservative|en>ru|ctx0": "fc95be993eea0b84241d4a42",
    "translate|toc_translate|conservative|en>ru|ctx1": "c27f868c3df54575ac93f63d",
    "translate|toc_translate|conservative|auto>ru|ctx0": "a033fc48784497a93e86c230",
    "translate|toc_translate|conservative|auto>ru|ctx1": "2fab9c47bbd3a4a1286e1b0d",
    "translate|toc_translate|conservative|ru>ru|ctx0": "450f56fbf464776f9c181f39",
    "translate|toc_translate|conservative|ru>ru|ctx1": "78e5954cfe31bc6eae7b1ffa",
    "translate|toc_translate|conservative|de>en|ctx0": "3e75b83f9f75f621eeca1739",
    "translate|toc_translate|conservative|de>en|ctx1": "5433c8f48085051d01812bb3",
    "translate|toc_translate|literary|en>ru|ctx0": "7e14dc49a7448a060f2a84e5",
    "translate|toc_translate|literary|en>ru|ctx1": "41415b74a3b0016bb0ae1ca6",
    "translate|toc_translate|literary|auto>ru|ctx0": "42bb747182a3e68765566b33",
    "translate|toc_translate|literary|auto>ru|ctx1": "82e1023d5b6e35981769f3c9",
    "translate|toc_translate|literary|ru>ru|ctx0": "e4f510763ee5dccd3227493d",
    "translate|toc_translate|literary|ru>ru|ctx1": "3373a29c43866c320e87f954",
    "translate|toc_translate|literary|de>en|ctx0": "c78efe40ce67e901811376fe",
    "translate|toc_translate|literary|de>en|ctx1": "26a41b1145c0ec8d6a664d53",
    "translate|literary_polish|conservative|en>ru|ctx0": "c9f26c73ab06857f9d4ae09a",
    "translate|literary_polish|conservative|en>ru|ctx1": "473df2cf37d2f78c93c8a46d",
    "translate|literary_polish|conservative|auto>ru|ctx0": "cc7c8ceaf55424dc0d823754",
    "translate|literary_polish|conservative|auto>ru|ctx1": "762ef75b8c529ff163382c89",
    "translate|literary_polish|conservative|ru>ru|ctx0": "e23f5ee1a5f155fc8d538e2f",
    "translate|literary_polish|conservative|ru>ru|ctx1": "216d90ffe73bac99d8bd37d8",
    "translate|literary_polish|conservative|de>en|ctx0": "eaacc16be9a01f1ea31db356",
    "translate|literary_polish|conservative|de>en|ctx1": "900208daca78058e5501fad0",
    "translate|literary_polish|literary|en>ru|ctx0": "9cb8d599f264549771e34691",
    "translate|literary_polish|literary|en>ru|ctx1": "2e48b4243dd3d8b902bdd0e6",
    "translate|literary_polish|literary|auto>ru|ctx0": "df9d8e3243b3a293842a870d",
    "translate|literary_polish|literary|auto>ru|ctx1": "37b307a60b9452e9a2def9bc",
    "translate|literary_polish|literary|ru>ru|ctx0": "9264a0374eac9a43d08d8b75",
    "translate|literary_polish|literary|ru>ru|ctx1": "1108f869ace094a84878edd4",
    "translate|literary_polish|literary|de>en|ctx0": "38a62f1c7ffe4a525496e9e8",
    "translate|literary_polish|literary|de>en|ctx1": "4d6f54c915818bfcc1db9a3e",
    "edit|default|conservative|en>ru|ctx0": "e258de258d87763939f54fa8",
    "edit|default|conservative|en>ru|ctx1": "e258de258d87763939f54fa8",
    "edit|default|conservative|auto>ru|ctx0": "8f20fa5dd68d9c03196f52e1",
    "edit|default|conservative|auto>ru|ctx1": "8f20fa5dd68d9c03196f52e1",
    "edit|default|conservative|ru>ru|ctx0": "53e1a8dd6d59bdcc4d7de2b1",
    "edit|default|conservative|ru>ru|ctx1": "53e1a8dd6d59bdcc4d7de2b1",
    "edit|default|conservative|de>en|ctx0": "12991e3025eaed800ae1f7fc",
    "edit|default|conservative|de>en|ctx1": "12991e3025eaed800ae1f7fc",
    "edit|default|literary|en>ru|ctx0": "ca175d913ed3a8b230b30151",
    "edit|default|literary|en>ru|ctx1": "ca175d913ed3a8b230b30151",
    "edit|default|literary|auto>ru|ctx0": "5e98fa8cba99fd63124e4a26",
    "edit|default|literary|auto>ru|ctx1": "5e98fa8cba99fd63124e4a26",
    "edit|default|literary|ru>ru|ctx0": "2f120024c1d50520708e5c6d",
    "edit|default|literary|ru>ru|ctx1": "2f120024c1d50520708e5c6d",
    "edit|default|literary|de>en|ctx0": "fab6b870a4351e16f7f19cb7",
    "edit|default|literary|de>en|ctx1": "fab6b870a4351e16f7f19cb7",
}
