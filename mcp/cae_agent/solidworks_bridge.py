from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pythoncom
import pywintypes
from win32com.client import dynamic


DOCUMENT_TYPES = {".sldprt": 1, ".sldasm": 2, ".slddrw": 3}


def _value_or_call(obj: Any, name: str, *args: Any) -> Any:
    value = getattr(obj, name)
    return value(*args) if callable(value) else value


def _connect() -> tuple[Any, bool]:
    """Attach to a running instance or create an isolated local-server instance."""
    try:
        unknown = pythoncom.GetActiveObject("SldWorks.Application")
        dispatch = unknown.QueryInterface(pythoncom.IID_IDispatch)
        return dynamic.Dispatch(dispatch), False
    except pywintypes.com_error:
        clsid = pywintypes.IID("SldWorks.Application")
        dispatch = pythoncom.CoCreateInstance(
            clsid,
            None,
            pythoncom.CLSCTX_LOCAL_SERVER,
            pythoncom.IID_IDispatch,
        )
        return dynamic.Dispatch(dispatch), True


def _open_document(application: Any, path: str, read_only: bool) -> tuple[Any, int]:
    suffix = Path(path).suffix.lower()
    if suffix not in DOCUMENT_TYPES:
        raise ValueError(f"Unsupported SolidWorks document extension: {path}")
    document_type = DOCUMENT_TYPES[suffix]
    options = 1 | (2 if read_only else 0)
    opened = application.OpenDoc6(path, document_type, options, "", 0, 0)
    document = opened[0] if isinstance(opened, tuple) else opened
    if document is None:
        raise RuntimeError(f"OpenDoc6 returned no document: {path}")
    return document, document_type


def _box_mm(values: Any) -> list[float] | None:
    if values is None:
        return None
    box = list(values)
    if len(box) < 6:
        return None
    return [float(value) * 1000.0 for value in box[:6]]


def _com_error(exc: Exception) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": type(exc).__name__,
        "message": str(exc),
    }
    if isinstance(exc, pywintypes.com_error):
        result["hresult"] = f"0x{exc.hresult & 0xFFFFFFFF:08X}"
        if exc.excepinfo:
            result["source"] = exc.excepinfo[1]
            result["description"] = exc.excepinfo[2]
    return result


def run(request: dict[str, Any]) -> dict[str, Any]:
    response: dict[str, Any] = {
        "status": "failed",
        "checks": {},
        "warnings": [],
        "error": None,
        "solidworks_revision": None,
    }
    application = None
    document = None
    created_application = False
    opened_document = False
    pythoncom.CoInitialize()
    try:
        application, created_application = _connect()
        if created_application or bool(request.get("visible", False)):
            application.Visible = bool(request.get("visible", False))
        response["solidworks_revision"] = str(
            _value_or_call(application, "RevisionNumber")
        )
        response["checks"]["attached_to_existing"] = not created_application
        response["checks"]["created_application"] = created_application
        response["checks"]["com_backend"] = "pywin32-dynamic-idispatch"

        operation = str(request.get("operation", ""))
        if operation == "ping":
            response["checks"]["connection"] = "ok"
            response["status"] = "succeeded"
            return response
        if operation not in {"inspect", "parameterize", "export"}:
            raise ValueError(f"Unsupported SolidWorks bridge operation: {operation}")

        input_path = str(Path(str(request["input_path"])).resolve())
        document, document_type = _open_document(
            application,
            input_path,
            read_only=operation != "parameterize",
        )
        opened_document = True
        response["checks"].update(
            {
                "document_type": document_type,
                "title": str(_value_or_call(document, "GetTitle")),
                "path": str(_value_or_call(document, "GetPathName")),
            }
        )

        if operation == "inspect":
            configurations = _value_or_call(document, "GetConfigurationNames") or []
            response["checks"]["configurations"] = [str(item) for item in configurations]

            features: list[dict[str, str]] = []
            feature = _value_or_call(document, "FirstFeature")
            guard = 0
            while feature is not None and guard < 10000:
                features.append(
                    {
                        "name": str(_value_or_call(feature, "Name")),
                        "type": str(_value_or_call(feature, "GetTypeName2")),
                    }
                )
                feature = _value_or_call(feature, "GetNextFeature")
                guard += 1
            response["checks"]["features"] = features
            response["checks"]["feature_count"] = len(features)

            dimensions: dict[str, float | None] = {}
            for name in request.get("dimension_names", []):
                dimension = document.Parameter(str(name))
                dimensions[str(name)] = (
                    None
                    if dimension is None
                    else float(_value_or_call(dimension, "SystemValue")) * 1000.0
                )
            response["checks"]["dimensions_mm"] = dimensions

            bodies: list[dict[str, Any]] = []
            if document_type == 1:
                for body in document.GetBodies2(0, False) or []:
                    bodies.append(
                        {
                            "name": str(_value_or_call(body, "Name")),
                            "bounding_box_mm": _box_mm(
                                _value_or_call(body, "GetBodyBox")
                            ),
                        }
                    )
            response["checks"]["bodies"] = bodies
            response["checks"]["body_count"] = len(bodies)

        elif operation == "parameterize":
            changes: list[dict[str, Any]] = []
            for name, value in request["dimensions_mm"].items():
                dimension = document.Parameter(str(name))
                if dimension is None:
                    raise RuntimeError(f"Dimension not found: {name}")
                old_mm = float(_value_or_call(dimension, "SystemValue")) * 1000.0
                dimension.SystemValue = float(value) / 1000.0
                changes.append(
                    {
                        "name": str(name),
                        "old_mm": old_mm,
                        "new_mm": float(_value_or_call(dimension, "SystemValue"))
                        * 1000.0,
                    }
                )
            response["checks"]["dimension_changes"] = changes
            response["checks"]["rebuilt"] = bool(document.ForceRebuild3(False))
            saved = document.Save3(1, 0, 0)
            saved_value = saved[0] if isinstance(saved, tuple) else saved
            if not bool(saved_value):
                raise RuntimeError("Save3 returned false")
            response["checks"]["saved"] = True

            export_path = request.get("export_path")
            if export_path:
                export_path = str(Path(str(export_path)).resolve())
                export_code = int(document.SaveAs3(export_path, 0, 1))
                if not Path(export_path).is_file():
                    raise RuntimeError(
                        f"SolidWorks did not create export file: "
                        f"code={export_code} path={export_path}"
                    )
                response["checks"]["export_path"] = export_path
                response["checks"]["export_code"] = export_code

        elif operation == "export":
            export_path = str(Path(str(request["export_path"])).resolve())
            export_code = int(document.SaveAs3(export_path, 0, 1))
            if not Path(export_path).is_file():
                raise RuntimeError(
                    f"SolidWorks did not create export file: "
                    f"code={export_code} path={export_path}"
                )
            response["checks"]["export_path"] = export_path
            response["checks"]["export_code"] = export_code

        response["status"] = "succeeded"
        return response
    except Exception as exc:
        details = _com_error(exc)
        response["error"] = details["message"]
        response["checks"]["exception"] = details
        return response
    finally:
        if opened_document and document is not None and application is not None:
            try:
                application.CloseDoc(str(_value_or_call(document, "GetTitle")))
            except Exception as exc:
                response["warnings"].append(
                    f"Could not close the SolidWorks document cleanly: {exc}"
                )
        if created_application and application is not None:
            try:
                application.ExitApp()
            except Exception as exc:
                response["warnings"].append(
                    f"Could not close the SolidWorks application cleanly: {exc}"
                )
        document = None
        application = None
        pythoncom.CoUninitialize()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--response", required=True)
    args = parser.parse_args()
    request_path = Path(args.request).resolve()
    response_path = Path(args.response).resolve()
    response = run(json.loads(request_path.read_text(encoding="utf-8-sig")))
    response_path.write_text(
        json.dumps(response, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0 if response.get("status") == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
