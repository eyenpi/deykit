"""Current labels use (decision, dataset) scope and stable (case, question) IDs."""

from deykit.contracts.identities import validate_resource_id
from deykit.contracts.json_value import semantic_hash


def label_id(case_id: str, question_id: str) -> str:
    validate_resource_id(case_id)
    validate_resource_id(question_id)
    return "label-" + semantic_hash([case_id, question_id])
