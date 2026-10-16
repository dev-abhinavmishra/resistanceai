"""Core-logic tests for ResistanceAI.

Run from the repo root:  python -m unittest discover -s tests -v

These cover the pure transformation/validation layer — input normalization,
biomarker spelling families, cohort identity, and API payload validation —
which is where misattributed biology would silently corrupt a prediction.
The trained artifact is intentionally not required here (it is gitignored
anyway, so tests must pass on a clean checkout).
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from backend.corpus import record_uid, record_sample_uid
from backend.data_ingestion import ClinicalDataIngestor
from backend.features import (canonical_cancer_type, fusion_gene_set,
                              is_msi_unstable, normalize_clinical_input,
                              normalize_msi_type)
from backend.main import _validate_clinical_input


class TestCanonicalCancerType(unittest.TestCase):
    def test_common_sites(self):
        self.assertEqual(canonical_cancer_type("Lung Adenocarcinoma"), "lung")
        self.assertEqual(canonical_cancer_type("Invasive Breast Carcinoma"),
                         "breast")
        self.assertEqual(canonical_cancer_type("Intrahepatic "
                                               "Cholangiocarcinoma"),
                         "hepatobiliary")
        self.assertEqual(canonical_cancer_type("Uterine Mixed Endometrial "
                                               "Carcinoma"), "endometrial")

    def test_unknown_and_empty(self):
        self.assertEqual(canonical_cancer_type("Xeno Tumor 9000"), "other")
        self.assertEqual(canonical_cancer_type(None), "other")
        self.assertEqual(canonical_cancer_type(""), "other")


class TestMsiSpellings(unittest.TestCase):
    def test_unstable_family(self):
        for v in ("Unstable", "Instable", "MSI-H", "MSI-High", "msih", "high"):
            self.assertTrue(is_msi_unstable(v), v)
            self.assertEqual(normalize_msi_type(v), "Unstable", v)

    def test_stable_family(self):
        for v in ("Stable", "MSS", "MSI-L", "low"):
            self.assertFalse(is_msi_unstable(v), v)
            self.assertEqual(normalize_msi_type(v), "Stable", v)

    def test_unknown_returns_none(self):
        self.assertIsNone(normalize_msi_type("not reported"))
        self.assertIsNone(normalize_msi_type(None))


class TestPatientIdentity(unittest.TestCase):
    def test_uid_is_cohort_qualified(self):
        rec = {"cohort": "chord", "patient_id": "P-0001234",
               "sample_id": "P-0001234-T01"}
        self.assertEqual(record_uid(rec), "chord:P-0001234")
        self.assertEqual(record_sample_uid(rec), "chord:P-0001234-T01")

    def test_same_bare_id_different_cohort_is_different_patient(self):
        a = {"cohort": "impact2017", "patient_id": "P-0001234"}
        b = {"cohort": "chord", "patient_id": "P-0001234"}
        self.assertNotEqual(record_uid(a), record_uid(b))


class TestFusionGeneSet(unittest.TestCase):
    def test_dict_and_string_forms(self):
        self.assertEqual(fusion_gene_set([{"gene1": "EML4", "gene2": "ALK"}]),
                         {"EML4", "ALK"})
        self.assertEqual(fusion_gene_set(["EML4-ALK"]), {"EML4", "ALK"})
        self.assertEqual(fusion_gene_set(["EML4_ALK"]), {"EML4", "ALK"})
        self.assertEqual(fusion_gene_set(None), set())
        self.assertEqual(fusion_gene_set([]), set())


class TestNormalizeClinicalInput(unittest.TestCase):
    def test_legacy_tmb_level(self):
        ci = normalize_clinical_input({"tmb_level": "tmb_3",
                                       "cancer_type": "lung"})
        self.assertEqual(ci["tmb"], 15.0)
        self.assertEqual(ci["cancer_type_canonical"], "lung")

    def test_legacy_ct_transition_becomes_fraction(self):
        ci = normalize_clinical_input({"ct_transition_pct": 65.2})
        self.assertAlmostEqual(ci["spectrum_fractions"]["C>T"], 0.652)

    def test_protein_label_is_mutation_not_fusion(self):
        ci = normalize_clinical_input({"detected_variants": ["BRAF-V600E"]})
        self.assertIn("BRAF", ci["gene_mutations"])
        self.assertFalse(ci.get("fusions"))

    def test_gene_pair_label_is_fusion_not_mutation(self):
        ci = normalize_clinical_input({"detected_variants": ["EML4-ALK"]})
        self.assertIn("EML4-ALK", ci["fusions"])
        self.assertNotIn("EML4", ci.get("gene_mutations") or [])

    def test_cna_label_becomes_copy_number_event(self):
        ci = normalize_clinical_input({"detected_variants": ["MYC_AMP"]})
        self.assertEqual(ci["cna"]["MYC"], 2)

    def test_biomarker_labels(self):
        ci = normalize_clinical_input(
            {"detected_variants": ["MSI-H", "TMB-H", "HRD_Positive"]})
        self.assertEqual(ci["msi_type"], "Unstable")
        self.assertGreaterEqual(ci["tmb"], 10)
        self.assertEqual(ci["hr_deficiency"], "present")

    def test_sample_type_defaults_from_stage(self):
        self.assertEqual(normalize_clinical_input({"stage": "IV"})["sample_type"],
                         "Metastasis")
        self.assertEqual(normalize_clinical_input({"stage": "II"})["sample_type"],
                         "Primary")


class TestGenomicReportIngest(unittest.TestCase):
    REPORT = {
        "report_id": "NGS-2024-001", "patient_id": "PX-9921",
        "biomarkers": {"tmb": 18.5, "hrd_status": "positive",
                       "msi_status": "MSS", "signature_1_weight": 65.2,
                       "sv_count": 14},
        "variants": [
            {"gene": "EGFR", "alteration": "L858R", "vaf": 0.22, "type": "SNP"},
            {"gene": "TP53", "alteration": "R175H", "vaf": 0.45, "type": "SNP"},
        ],
    }

    def setUp(self):
        import json
        self.ci = ClinicalDataIngestor.ingest_genomic_report(
            json.dumps(self.REPORT))

    def test_driver_genes_and_protein_changes(self):
        self.assertEqual(self.ci["gene_mutations"], ["EGFR", "TP53"])
        details = {d["gene"]: d["protein_change"]
                   for d in self.ci["mutation_details"]}
        self.assertEqual(details["EGFR"], "L858R")

    def test_biomarker_mappings(self):
        self.assertEqual(self.ci["tmb"], 18.5)
        self.assertEqual(self.ci["hr_deficiency"], "present")
        self.assertEqual(self.ci["msi_type"], "Stable")
        self.assertEqual(self.ci["sv_count"], 14)
        self.assertAlmostEqual(self.ci["spectrum_fractions"]["C>T"], 0.652)

    def test_bad_json_raises(self):
        with self.assertRaises(ValueError):
            ClinicalDataIngestor.ingest_genomic_report("not json {")


class TestApiValidation(unittest.TestCase):
    def test_valid_minimal_payload(self):
        errors, _ = _validate_clinical_input(
            {"cancer_type": "breast", "stage": "IV"})
        self.assertEqual(errors, [])

    def test_empty_payload_rejected(self):
        errors, _ = _validate_clinical_input({})
        self.assertTrue(errors)

    def test_bool_is_not_numeric(self):
        errors, _ = _validate_clinical_input({"tmb": True})
        self.assertTrue(any("tmb" in e for e in errors))

    def test_bad_stage_rejected(self):
        errors, _ = _validate_clinical_input({"stage": "V"})
        self.assertTrue(any("stage" in e for e in errors))

    def test_gene_mutations_must_be_string_list(self):
        errors, _ = _validate_clinical_input({"gene_mutations": "EGFR"})
        self.assertTrue(any("gene_mutations" in e for e in errors))

    def test_one_sided_fusion_string_rejected(self):
        errors, _ = _validate_clinical_input({"fusions": ["ALK"]})
        self.assertTrue(any("fusions" in e for e in errors))

    def test_unknown_fields_warn_not_error(self):
        errors, warnings = _validate_clinical_input(
            {"cancer_type": "lung", "stage": "III", "mystery_field": 1})
        self.assertEqual(errors, [])
        self.assertTrue(any("mystery_field" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
