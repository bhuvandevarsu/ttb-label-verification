# Demo Test Matrix

| Fixture | Scenario | Expected behavior |
|---|---|---|
| `01_pass_clean.jpg` | Clean label | PASS |
| `02_pass_rotated.jpg` | Mild camera rotation | PASS or NEEDS REVIEW depending on OCR confidence |
| `03_pass_glare.jpg` | Lighting/glare | PASS or NEEDS REVIEW; result should expose OCR confidence |
| `04_fail_warning.jpg` | Government warning altered | FAIL with warning-specific reason |
| `05_review_rotated_glare.jpg` | Rotation + glare | NEEDS REVIEW is acceptable when OCR confidence is low |
| `06_fail_abv.jpg` | ABV changed to 40% | FAIL with ABV mismatch |

The fixtures are synthetic demonstration labels, not official TTB label approvals.
