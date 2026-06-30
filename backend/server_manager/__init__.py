import inspect
import pkgutil
import types
import typing
from typing import Union, get_args, get_origin
from pydantic import BaseModel
from pydantic_core import PydanticUndefined

import remnawave.models


def _is_optional(annotation: typing.Any) -> bool:
    if annotation is type(None):
        return True
    origin = get_origin(annotation)
    if origin is Union or (hasattr(types, "UnionType") and origin is types.UnionType):
        return type(None) in get_args(annotation)
    return False


def _patch_remnawave_models() -> None:
    package = remnawave.models
    modules = []
    for _, module_name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        try:
            modules.append(__import__(module_name, fromlist=["*"]))
        except Exception:
            continue

    all_models = []
    for mod in modules:
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, BaseModel) and obj is not BaseModel:
                all_models.append(obj)

    # First, modify all fields across all models
    for obj in all_models:
        for field in obj.model_fields.values():
            if field.default is PydanticUndefined and _is_optional(field.annotation):
                field.default = None

    # Then rebuild all models multiple times to resolve nested schemas
    for _ in range(3):
        for obj in all_models:
            try:
                obj.model_rebuild(force=True)
            except Exception:
                pass


_patch_remnawave_models()
