# So sánh OCR trên 84 trang

Độ giống văn bản (0 đến 1, trung bình theo trang):

| Cặp | Trung bình | Thấp nhất |
|---|---|---|
| Vintern-1B và MinerU | 0.71 | 0.16 |
| Vintern-1B và OpenAI | 0.69 | 0.03 |
| MinerU và OpenAI | 0.87 | 0.02 |

Trên 57 trang MinerU và OpenAI giống nhau từ 0,9 trở lên (tham chiếu đáng tin hơn): Vintern-1B giống MinerU trung bình 0.73, giống OpenAI 0.73.

Số liệu (số, ngày, số hiệu văn bản). *Không được ủng hộ* = chỉ engine này đọc ra, hai engine kia không; *bỏ sót* = hai engine kia cùng đọc ra mà engine này không.

| Engine | Token | Không được ủng hộ | Bỏ sót so với đồng thuận | Trang lặp chữ | Trang rỗng | Dòng bảng |
|---|---|---|---|---|---|---|
| mineru | 933 | 40 (4.3%) | 5 / 560 (0.9%) | 0 | 0 | 294 |
| vintern1b | 770 | 161 (20.9%) | 289 / 844 (34.2%) | 6 | 0 | 501 |
| openai | 883 | 34 (3.9%) | 49 / 604 (8.1%) | 2 | 1 | 413 |

## Trang Vintern-1B khác MinerU nhiều nhất

| Trang | Vintern–MinerU | Vintern–OpenAI | MinerU–OpenAI |
|---|---|---|---|
| 66CNTI_p05 | 0.16 | 0.29 | 0.99 |
| 1658CNTI_p17 | 0.17 | 0.17 | 0.96 |
| 1650CNTI_p08 | 0.19 | 0.19 | 0.99 |
| 1650CNTI_p18 | 0.20 | 0.20 | 0.96 |
| 549CNTI_p02 | 0.24 | 0.24 | 0.96 |
| 66CNTI_p03 | 0.26 | 0.30 | 0.65 |
| 4748DNTI_p03 | 0.28 | 0.28 | 0.99 |
| 1650CNTI_p07 | 0.34 | 0.33 | 0.99 |
| 66CNTI_p20 | 0.35 | 0.35 | 0.99 |
| 1658CNTI_p04 | 0.37 | 0.55 | 0.68 |

## Token chỉ vintern1b đọc ra (20 đầu)

`1028/NHNO` (1028KHTI_p01), `388/NHN` (1028KHTI_p01), `5201/NHNO-ALCO` (1028KHTI_p01), `1650/NHNo.TH-KHCN` (1650CNTI_p01), `14/15/2026` (1650CNTI_p04), `387/NHo-TKH` (1650CNTI_p05), `7.7%` (1650CNTI_p05), `8.2%` (1650CNTI_p05), `8.4%` (1650CNTI_p05), `0.4%` (1650CNTI_p06), `75%` (1650CNTI_p07), `7956/NHNo-KHCN` (1650CNTI_p09), `0597` (1650CNTI_p12), `30/02/2026` (1650CNTI_p13), `2001` (1650CNTI_p14), `10` (1650CNTI_p17), `11` (1650CNTI_p17), `14/05/2026` (1650CNTI_p19), `7956/NHNO-KHCN` (1650CNTI_p20), `1658/NHNo.TH-KHCN` (1658CNTI_p01)

## Token chỉ mineru đọc ra (20 đầu)

`14` (1650CNTI_p04), `1650` (1650CNTI_p04), `2026` (1650CNTI_p04), `1801/NH-No-ALCO` (1650CNTI_p05), `0.4` (1650CNTI_p06), `1650` (1650CNTI_p06), `5749` (1650CNTI_p12), `14` (1650CNTI_p13), `2026` (1650CNTI_p13), `30/01/2026` (1650CNTI_p13), `61` (1650CNTI_p13), `79562026` (1650CNTI_p17), `20174` (1650CNTI_p19), `7956` (1650CNTI_p20), `1658` (1658CNTI_p04), `986` (1658CNTI_p11), `14/15/2026` (1658CNTI_p13), `74` (1658CNTI_p13), `11` (1658CNTI_p17), `1801/NHNo-ALCQ` (1866CNTI_p02)

## Token chỉ openai đọc ra (20 đầu)

`2268/QyĐ-NHNo-TĐ` (1650CNTI_p01), `4466/QyĐ-NHNo-TĐ` (1650CNTI_p01), `14/05/2026` (1650CNTI_p04), `7.5` (1650CNTI_p07), `14/05/2026` (1650CNTI_p13), `79.56` (1650CNTI_p20), `168` (1658CNTI_p04), `19/05/2026` (1658CNTI_p04), `7.5` (1658CNTI_p07), `14` (1658CNTI_p13), `2026` (1658CNTI_p13), `7955` (1658CNTI_p13), `7955` (1658CNTI_p19), `7955` (1658CNTI_p21), `9501` (1866CNTI_p02), `05` (1866CNTI_p03), `214` (214KHTI_p01), `13/BC05` (4748DNTI_p02), `01/04/2026` (66CNTI_p10), `12` (66CNTI_p10)
