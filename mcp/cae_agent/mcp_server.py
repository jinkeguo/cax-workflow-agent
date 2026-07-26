from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable

from . import __version__
from .abaqus import ensure_component_elsets, validate_abaqus_mesh
from .abaqus_post import (
    extract_abaqus_failure_indices,
    extract_abaqus_field,
    extract_abaqus_path,
    render_abaqus_contour,
)
from .abaqus_runtime import (
    cancel_abaqus_job,
    get_abaqus_environment,
    inspect_abaqus_job,
    monitor_abaqus_job,
    retry_abaqus_job,
    run_abaqus_datacheck,
    submit_abaqus_job,
    summarize_abaqus_odb,
)
from .diagnostics import diagnose_cae_failure
from .hypermesh import (
    check_hm_mesh_quality,
    export_abaqus_deck,
    inspect_hm_model,
    mesh_hm_solids,
    smooth_hm_solid_mesh,
)
from .manifest import get_case_status, record_case_stage
from .planner import get_cae_capabilities, plan_next_action
from .research import (
    evaluate_failure_research,
    prepare_failure_research,
    record_verified_failure_rule,
)
from .solidworks import (
    export_solidworks_document,
    get_solidworks_environment,
    inspect_solidworks_document,
    instantiate_solidworks_template,
    test_solidworks_connection,
)

PROTOCOL_VERSION = "2025-06-18"

TOOLS = [
    {
        "name": "diagnose_cae_failure",
        "title": "Diagnose CAE Failure",
        "description": "Classify SolidWorks, HyperMesh, or Abaqus errors and return likely causes, bounded recovery actions, approval boundaries, and the next recommended MCP tool.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "application": {
                    "type": "string",
                    "enum": ["auto", "solidworks", "hypermesh", "abaqus"],
                    "default": "auto"
                },
                "stage": {"type": "string"},
                "log_text": {"type": "string"},
                "log_path": {"type": "string"},
                "knowledge_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 10
                }
            },
            "additionalProperties": False
        },
    },
    {
        "name": "prepare_failure_research",
        "title": "Prepare Failure Web Research",
        "description": "Extract a stable error signature and create official-documentation-first web search queries for a SolidWorks, HyperMesh, or Abaqus failure.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "application": {
                    "type": "string",
                    "enum": ["solidworks", "hypermesh", "abaqus"]
                },
                "error_text": {"type": "string"},
                "stage": {"type": "string"}
            },
            "required": ["application", "error_text"],
            "additionalProperties": False
        },
    },
    {
        "name": "evaluate_failure_research",
        "title": "Evaluate Failure Web Research",
        "description": "Rank extracted web evidence by authority and relevance, then produce an unverified failure-rule candidate with explicit promotion gates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "application": {
                    "type": "string",
                    "enum": ["solidworks", "hypermesh", "abaqus"]
                },
                "error_text": {"type": "string"},
                "stage": {"type": "string"},
                "candidates": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 20,
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "title": {"type": "string"},
                            "excerpt": {"type": "string"},
                            "cause": {"type": "string"},
                            "solution": {"type": "string"},
                            "product_version": {"type": "string"},
                            "recommended_actions": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["url", "title", "excerpt"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["application", "error_text", "candidates"],
            "additionalProperties": False
        },
    },
    {
        "name": "record_verified_failure_rule",
        "title": "Record Verified Failure Rule",
        "description": "Preview or atomically append a web-researched failure rule to a local registry only after bounded recovery has been verified.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "registry_path": {"type": "string"},
                "candidate_rule": {"type": "object"},
                "verification_evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1
                },
                "idempotency_key": {"type": "string", "minLength": 1},
                "confirm_write": {"type": "boolean", "default": False},
                "expected_registry_sha256": {"type": "string"}
            },
            "required": [
                "registry_path",
                "candidate_rule",
                "verification_evidence",
                "idempotency_key"
            ],
            "additionalProperties": False
        },
    },
    {
        "name": "inspect_hm_model",
        "title": "Inspect HyperMesh Model",
        "description": "Read a HyperMesh .hm model in isolated batch mode and return entity and element counts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 600, "default": 60},
            },
            "required": ["input_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "export_abaqus_deck",
        "title": "Export Abaqus Deck",
        "description": "Export a HyperMesh model to an Abaqus .inp deck with an atomic output handoff.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string"},
                "output_path": {"type": "string"},
                "overwrite": {"type": "boolean", "default": False},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 1800, "default": 120},
            },
            "required": ["input_path", "output_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "ensure_component_elsets",
        "title": "Ensure Abaqus Component ELSETs",
        "description": "Add ELSET parameters to HyperMesh-exported element blocks using HW_COMPONENT comments.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string"},
                "output_path": {"type": "string"},
                "overwrite": {"type": "boolean", "default": False},
            },
            "required": ["input_path", "output_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "validate_abaqus_mesh",
        "title": "Validate Abaqus Mesh",
        "description": "Check node references, duplicate connectivity, element types, bounding box, and hex center Jacobians.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string"},
                "expected_type": {"type": "string"},
                "expected_elements": {"type": "integer", "minimum": 0},
            },
            "required": ["input_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_case_status",
        "title": "Get CAE Case Status",
        "description": "Read a CAE case manifest, verify artifacts and hashes, and return stage status.",
        "inputSchema": {
            "type": "object",
            "properties": {"manifest_path": {"type": "string"}},
            "required": ["manifest_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_cae_capabilities",
        "title": "Get CAE Adapter Capabilities",
        "description": "Report which CAD, meshing, solver, and postprocessing adapters are actually available.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "plan_next_action",
        "title": "Plan Next CAE Action",
        "description": "Read a case manifest and choose one bounded next operation, its tool arguments, and approval boundary.",
        "inputSchema": {
            "type": "object",
            "properties": {"manifest_path": {"type": "string"}},
            "required": ["manifest_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_case_stage",
        "title": "Record CAE Case Stage",
        "description": "Preview or atomically record a verified stage result in a case manifest with hash and idempotency checks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "manifest_path": {"type": "string"},
                "stage": {"type": "string", "enum": ["cad", "mesh", "deck", "solve", "post"]},
                "stage_status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "passed", "failed"]
                },
                "evidence": {"type": "array", "items": {"type": "string"}},
                "idempotency_key": {"type": "string", "minLength": 1},
                "expected_manifest_sha256": {"type": "string"},
                "confirm_write": {"type": "boolean", "default": False}
            },
            "required": [
                "manifest_path",
                "stage",
                "stage_status",
                "evidence",
                "idempotency_key"
            ],
            "additionalProperties": False
        },
    },
    {
        "name": "get_abaqus_environment",
        "title": "Get Abaqus Environment",
        "description": "Query the installed Abaqus release and command availability.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 120, "default": 30}
            },
            "additionalProperties": False
        },
    },
    {
        "name": "run_abaqus_datacheck",
        "title": "Run Abaqus Datacheck",
        "description": "Run an isolated Abaqus datacheck on a flattened input deck and retain all diagnostic artifacts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string"},
                "job_name": {"type": "string", "default": "cae_datacheck"},
                "cpus": {"type": "integer", "minimum": 1, "maximum": 64, "default": 1},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 1800, "default": 300}
            },
            "required": ["input_path"],
            "additionalProperties": False
        },
    },
    {
        "name": "inspect_abaqus_job",
        "title": "Inspect Abaqus Job",
        "description": "Read Abaqus job files and classify the job as completed, running, failed, or unknown.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_directory": {"type": "string"},
                "job_name": {"type": "string"}
            },
            "required": ["job_directory", "job_name"],
            "additionalProperties": False
        },
    },
    {
        "name": "summarize_abaqus_odb",
        "title": "Summarize Abaqus ODB",
        "description": "Use Abaqus Python to list ODB steps, frames, field outputs, and root sets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 600, "default": 120}
            },
            "required": ["input_path"],
            "additionalProperties": False
        },
    },
    {
        "name": "get_solidworks_environment",
        "title": "Get SolidWorks Environment",
        "description": "Detect SolidWorks desktop COM registration and executable availability without launching the application.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        },
    },
    {
        "name": "test_solidworks_connection",
        "title": "Test SolidWorks Connection",
        "description": "Launch or attach to SolidWorks, query its revision through COM, and exit a newly created test instance without opening a document.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "visible": {"type": "boolean", "default": False},
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 300,
                    "default": 90
                }
            },
            "additionalProperties": False
        },
    },
    {
        "name": "inspect_solidworks_document",
        "title": "Inspect SolidWorks Document",
        "description": "Open a SolidWorks document read-only and list configurations, features, solid bodies, bounding boxes, and requested named dimensions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string"},
                "dimension_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": []
                },
                "visible": {"type": "boolean", "default": False},
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 600,
                    "default": 120
                }
            },
            "required": ["input_path"],
            "additionalProperties": False
        },
    },
    {
        "name": "instantiate_solidworks_template",
        "title": "Instantiate SolidWorks Template",
        "description": "Create a new .SLDPRT from a parameterized template, set fully qualified dimensions in millimetres, rebuild, save, and optionally export a neutral CAD file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_path": {"type": "string"},
                "output_native_path": {"type": "string"},
                "dimensions_mm": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                    "minProperties": 1
                },
                "export_path": {"type": "string"},
                "overwrite": {"type": "boolean", "default": False},
                "confirm_write": {"type": "boolean", "default": False},
                "visible": {"type": "boolean", "default": False},
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 900,
                    "default": 180
                }
            },
            "required": [
                "template_path",
                "output_native_path",
                "dimensions_mm"
            ],
            "additionalProperties": False
        },
    },
    {
        "name": "export_solidworks_document",
        "title": "Export SolidWorks Document",
        "description": "Export an existing SolidWorks part or assembly to STEP, Parasolid, or IGES through an isolated staging file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string"},
                "output_path": {"type": "string"},
                "overwrite": {"type": "boolean", "default": False},
                "confirm_write": {"type": "boolean", "default": False},
                "visible": {"type": "boolean", "default": False},
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 900,
                    "default": 180
                }
            },
            "required": ["input_path", "output_path"],
            "additionalProperties": False
        },
    },
    {
        "name": "mesh_hm_solids",
        "title": "Map Mesh HyperMesh Solids",
        "description": "Preview or run HyperMesh 2025 multi-solid mapped meshing for explicitly selected solid IDs and save a derived native model.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string"},
                "output_path": {"type": "string"},
                "solid_ids": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1},
                    "minItems": 1
                },
                "element_size": {"type": "number", "exclusiveMinimum": 0},
                "source_element_type": {
                    "type": "string",
                    "enum": ["tria", "quad", "mixed"],
                    "default": "quad"
                },
                "overwrite": {"type": "boolean", "default": False},
                "confirm_mesh": {"type": "boolean", "default": False},
                "timeout_seconds": {
                    "type": "integer", "minimum": 1, "maximum": 3600, "default": 600
                }
            },
            "required": ["input_path", "output_path", "solid_ids", "element_size"],
            "additionalProperties": False
        },
    },
    {
        "name": "check_hm_mesh_quality",
        "title": "Check HyperMesh 3D Mesh Quality",
        "description": "Run Abaqus-method HyperMesh 3D Jacobian, aspect, and optional minimum-length checks and return failed element IDs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string"},
                "jacobian_min": {
                    "type": "number", "exclusiveMinimum": 0, "maximum": 1, "default": 0.6
                },
                "aspect_max": {
                    "type": "number", "exclusiveMinimum": 1, "default": 5.0
                },
                "min_length": {"type": "number", "minimum": 0, "default": 0},
                "timeout_seconds": {
                    "type": "integer", "minimum": 1, "maximum": 600, "default": 120
                }
            },
            "required": ["input_path"],
            "additionalProperties": False
        },
    },
    {
        "name": "smooth_hm_solid_mesh",
        "title": "Smooth HyperMesh Solid Mesh",
        "description": "Preview or smooth interior nodes of explicitly selected solid elements and save a derived HyperMesh model.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string"},
                "output_path": {"type": "string"},
                "element_ids": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1},
                    "minItems": 1
                },
                "iterations": {
                    "type": "integer", "minimum": 1, "maximum": 50, "default": 5
                },
                "overwrite": {"type": "boolean", "default": False},
                "confirm_repair": {"type": "boolean", "default": False},
                "timeout_seconds": {
                    "type": "integer", "minimum": 1, "maximum": 600, "default": 180
                }
            },
            "required": ["input_path", "output_path", "element_ids"],
            "additionalProperties": False
        },
    },
    {
        "name": "submit_abaqus_job",
        "title": "Submit Abaqus Analysis",
        "description": "Preview or submit a flattened Abaqus input deck as a background job in an explicit job directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string"},
                "job_directory": {"type": "string"},
                "job_name": {"type": "string"},
                "cpus": {"type": "integer", "minimum": 1, "maximum": 64, "default": 1},
                "confirm_submit": {"type": "boolean", "default": False},
                "timeout_seconds": {
                    "type": "integer", "minimum": 1, "maximum": 600, "default": 60
                }
            },
            "required": ["input_path", "job_directory", "job_name"],
            "additionalProperties": False
        },
    },
    {
        "name": "monitor_abaqus_job",
        "title": "Monitor Abaqus Analysis",
        "description": "Read Abaqus job artifacts and return state, progress tail, increments, warnings, errors, and ODB availability.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_directory": {"type": "string"},
                "job_name": {"type": "string"}
            },
            "required": ["job_directory", "job_name"],
            "additionalProperties": False
        },
    },
    {
        "name": "cancel_abaqus_job",
        "title": "Cancel Abaqus Analysis",
        "description": "Preview or terminate a currently running Abaqus job using the Abaqus execution procedure.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_directory": {"type": "string"},
                "job_name": {"type": "string"},
                "confirm_cancel": {"type": "boolean", "default": False},
                "timeout_seconds": {
                    "type": "integer", "minimum": 1, "maximum": 600, "default": 60
                }
            },
            "required": ["job_directory", "job_name"],
            "additionalProperties": False
        },
    },
    {
        "name": "retry_abaqus_job",
        "title": "Retry Abaqus Analysis",
        "description": "Retry the unchanged submitted deck under a new job name only for approved transient runtime reasons.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_directory": {"type": "string"},
                "previous_job_name": {"type": "string"},
                "new_job_name": {"type": "string"},
                "retry_reason": {
                    "type": "string",
                    "enum": ["runtime-transient", "license-restored", "user-cancelled"]
                },
                "cpus": {"type": "integer", "minimum": 1, "maximum": 64, "default": 1},
                "confirm_submit": {"type": "boolean", "default": False},
                "timeout_seconds": {
                    "type": "integer", "minimum": 1, "maximum": 600, "default": 60
                }
            },
            "required": [
                "job_directory", "previous_job_name", "new_job_name", "retry_reason"
            ],
            "additionalProperties": False
        },
    },
    {
        "name": "extract_abaqus_field",
        "title": "Extract Abaqus Field Data",
        "description": "Extract scalar, component, or invariant values from an ODB field into JSON and CSV with full extrema provenance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string"},
                "output_path": {"type": "string"},
                "field_name": {"type": "string"},
                "step_name": {"type": "string"},
                "frame_index": {"type": "integer", "default": -1},
                "set_name": {"type": "string"},
                "component": {"type": "string"},
                "invariant": {"type": "string"},
                "max_rows": {
                    "type": "integer", "minimum": 1, "maximum": 1000000, "default": 100000
                },
                "overwrite": {"type": "boolean", "default": False},
                "timeout_seconds": {
                    "type": "integer", "minimum": 1, "maximum": 1800, "default": 300
                }
            },
            "required": ["input_path", "output_path", "field_name"],
            "additionalProperties": False
        },
    },
    {
        "name": "extract_abaqus_path",
        "title": "Extract Abaqus Path Data",
        "description": "Extract ODB XY data along an ordered node-list path using Abaqus Viewer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string"},
                "output_path": {"type": "string"},
                "instance_name": {"type": "string"},
                "node_labels": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1},
                    "minItems": 2
                },
                "field_name": {"type": "string"},
                "position": {
                    "type": "string",
                    "enum": ["nodal", "integration_point", "element_nodal", "centroid"],
                    "default": "nodal"
                },
                "step_name": {"type": "string"},
                "frame_index": {"type": "integer", "default": -1},
                "component": {"type": "string"},
                "invariant": {"type": "string"},
                "overwrite": {"type": "boolean", "default": False},
                "timeout_seconds": {
                    "type": "integer", "minimum": 1, "maximum": 1800, "default": 300
                }
            },
            "required": [
                "input_path", "output_path", "instance_name", "node_labels", "field_name"
            ],
            "additionalProperties": False
        },
    },
    {
        "name": "render_abaqus_contour",
        "title": "Render Abaqus Contour",
        "description": "Render a selected ODB field component or invariant to a PNG contour using Abaqus Viewer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string"},
                "output_path": {"type": "string"},
                "field_name": {"type": "string"},
                "position": {
                    "type": "string",
                    "enum": ["nodal", "integration_point", "element_nodal", "centroid"]
                },
                "step_name": {"type": "string"},
                "frame_index": {"type": "integer", "default": -1},
                "component": {"type": "string"},
                "invariant": {"type": "string"},
                "overwrite": {"type": "boolean", "default": False},
                "timeout_seconds": {
                    "type": "integer", "minimum": 1, "maximum": 1800, "default": 300
                }
            },
            "required": ["input_path", "output_path", "field_name", "position"],
            "additionalProperties": False
        },
    },
    {
        "name": "extract_abaqus_failure_indices",
        "title": "Extract Composite Failure Indices",
        "description": "Discover and summarize Abaqus-computed composite failure, damage-initiation, and damage variables with locations and section points.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string"},
                "output_path": {"type": "string"},
                "step_name": {"type": "string"},
                "frame_index": {"type": "integer", "default": -1},
                "overwrite": {"type": "boolean", "default": False},
                "timeout_seconds": {
                    "type": "integer", "minimum": 1, "maximum": 1800, "default": 300
                }
            },
            "required": ["input_path", "output_path"],
            "additionalProperties": False
        },
    },
]

HANDLERS: dict[str, Callable[..., Any]] = {
    "diagnose_cae_failure": diagnose_cae_failure,
    "prepare_failure_research": prepare_failure_research,
    "evaluate_failure_research": evaluate_failure_research,
    "record_verified_failure_rule": record_verified_failure_rule,
    "inspect_hm_model": inspect_hm_model,
    "export_abaqus_deck": export_abaqus_deck,
    "mesh_hm_solids": mesh_hm_solids,
    "check_hm_mesh_quality": check_hm_mesh_quality,
    "smooth_hm_solid_mesh": smooth_hm_solid_mesh,
    "ensure_component_elsets": ensure_component_elsets,
    "validate_abaqus_mesh": validate_abaqus_mesh,
    "get_case_status": get_case_status,
    "get_cae_capabilities": get_cae_capabilities,
    "plan_next_action": plan_next_action,
    "record_case_stage": record_case_stage,
    "get_abaqus_environment": get_abaqus_environment,
    "run_abaqus_datacheck": run_abaqus_datacheck,
    "inspect_abaqus_job": inspect_abaqus_job,
    "submit_abaqus_job": submit_abaqus_job,
    "monitor_abaqus_job": monitor_abaqus_job,
    "cancel_abaqus_job": cancel_abaqus_job,
    "retry_abaqus_job": retry_abaqus_job,
    "summarize_abaqus_odb": summarize_abaqus_odb,
    "extract_abaqus_field": extract_abaqus_field,
    "extract_abaqus_path": extract_abaqus_path,
    "render_abaqus_contour": render_abaqus_contour,
    "extract_abaqus_failure_indices": extract_abaqus_failure_indices,
    "get_solidworks_environment": get_solidworks_environment,
    "test_solidworks_connection": test_solidworks_connection,
    "inspect_solidworks_document": inspect_solidworks_document,
    "instantiate_solidworks_template": instantiate_solidworks_template,
    "export_solidworks_document": export_solidworks_document,
}


def _response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        payload["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": payload}


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return _response(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "cax-workflow-agent", "version": __version__},
                "instructions": (
                    "Use inspect and validation tools freely. Set overwrite=true only after "
                    "the user approves replacing an existing artifact."
                ),
            },
        )
    if method == "ping":
        return _response(request_id, {})
    if method == "tools/list":
        return _response(request_id, {"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        handler = HANDLERS.get(name)
        if handler is None:
            return _error(request_id, -32602, f"Unknown tool: {name}")
        try:
            value = handler(**arguments).to_dict()
            text = json.dumps(value, ensure_ascii=False, indent=2)
            return _response(
                request_id,
                {
                    "content": [{"type": "text", "text": text}],
                    "structuredContent": value,
                    "isError": value.get("status") == "failed",
                },
            )
        except TypeError as exc:
            return _error(request_id, -32602, f"Invalid tool arguments: {exc}")
        except Exception as exc:
            value = {
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
            return _response(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps(value)}],
                    "structuredContent": value,
                    "isError": True,
                },
            )
    if request_id is None:
        return None
    return _error(request_id, -32601, f"Method not found: {method}")


def main() -> None:
    for raw in sys.stdin:
        try:
            if not raw.strip():
                continue
            message = json.loads(raw)
            response = handle(message)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception:
            sys.stderr.write(traceback.format_exc())
            sys.stderr.flush()


if __name__ == "__main__":
    main()
