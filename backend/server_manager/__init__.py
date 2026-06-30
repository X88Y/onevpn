import inspect
import pkgutil
import types
import typing
from typing import List, Union, get_args, get_origin
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

import remnawave.models
from remnawave.models.hosts import HostResponseDto


def _is_optional(annotation: typing.Any) -> bool:
    if annotation is type(None):
        return True
    origin = get_origin(annotation)
    if origin is Union or (hasattr(types, "UnionType") and origin is types.UnionType):
        return type(None) in get_args(annotation)
    return False


def _patch_remnawave_models() -> None:
    # 1. Inject 'tags' field and 'tag' property into HostResponseDto
    if "tags" not in HostResponseDto.model_fields:
        field_info = FieldInfo(default_factory=list, alias="tags")
        field_info.annotation = List[str]
        HostResponseDto.model_fields["tags"] = field_info

    def get_tag(self: typing.Any) -> typing.Optional[str]:
        tags = getattr(self, "tags", None)
        if tags:
            return tags[0]
        return None

    HostResponseDto.tag = property(get_tag)  # type: ignore

    # 2. Patch all models
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

    # Modify all fields across all models
    for obj in all_models:
        for field in obj.model_fields.values():
            if field.default is PydanticUndefined and _is_optional(field.annotation):
                field.default = None

    # Rebuild all models multiple times to resolve nested schemas
    for _ in range(3):
        for obj in all_models:
            try:
                obj.model_rebuild(force=True)
            except Exception:
                pass


_patch_remnawave_models()
