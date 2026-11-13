# Milestone 1 comparison

All 1,076 input paths and SHA-256 hashes match the baseline.

| Mode | Run | Compiled | Meets target | Overall score | Grade |
| --- | --- | ---: | ---: | ---: | :---: |
| layout | before | 855 | 8 | 26.161% | F |
| layout | after | 883 | 492 | 67.391% | D |
| portable | before | 242 | 119 | 17.932% | F |
| portable | after | 589 | 275 | 41.688% | F |

Overall score averages the minimum page foreground SSIM for every PDF; failures and rejections count as zero. Portable passes at 90%; layout at 95%. Metrics and input limits are unchanged.

## Gains and regressions

- **layout:** 126 new compiles, 98 lost compiles; 484 new visual passes, 0 visual passes lost.
  Among 757 inputs compiled in both runs, 648 improved and 20 regressed by more than 1 percentage point. Mean minimum-page SSIM: 34.737% → 81.536%.
- **portable:** 347 new compiles, 0 lost compiles; 157 new visual passes, 1 visual passes lost.
  Among 242 inputs compiled in both runs, 78 improved and 16 regressed by more than 1 percentage point. Mean minimum-page SSIM: 79.732% → 83.288%.

Full per-input changes and status transitions are in [comparison.json](comparison.json). Open [comparison.html](comparison.html) for the interactive chart. See [results.json](results.json) for all current scores and [the baseline](../kaggle/FINDINGS.md) for the original findings.

## Largest coverage-adjusted regressions

| Mode | PDF | Before | After | Current outcome |
| --- | --- | ---: | ---: | --- |
| layout | `Pdf/ZKNFU42LM7BXETBTWEC42DOXCGU2MDLS.pdf` | 83.387% | 0% | compile_failed |
| layout | `Pdf/B4BDQGQ5WNDFTCQP46PNPZW2DUJ56GJH.pdf` | 70.852% | 0% | compile_failed |
| layout | `Pdf/STG36KDTBPEJTVEWCY734EISHQ5ZUVWF.pdf` | 46.238% | 0% | conversion_failed |
| layout | `Pdf/YE5PQJ6NUYA6UOWHADZIVVMCINU4AYZF.pdf` | 43.755% | 0% | conversion_failed |
| layout | `Pdf/YTZFSDRLFKSKIT5B6YTESDKRXLM2ZBWZ.pdf` | 42.018% | 0% | compile_failed |
| portable | `Pdf/HB2IHQ5EY4MV6YIJNCKSZ5L2EA6BPV75.pdf` | 73.953% | 59.573% | success |
| portable | `Pdf/SH2IQH724IFKG2K3GQ7RCDJ6Q7IJQLGE.pdf` | 73.463% | 59.947% | success |
| portable | `Pdf/SA3EKMNRN4KHJYVMDDBOUIQTZIV3ZVJH.pdf` | 66.127% | 53.127% | success |
| portable | `Pdf/IJEACIRWFTFAIA4OFQIWDFMFTRYC7SDS.pdf` | 75.771% | 62.897% | success |
| portable | `Pdf/666HXEHN6OLTL3QKGACG3DJ7UL4L5NWL.pdf` | 75.868% | 63.713% | success |
