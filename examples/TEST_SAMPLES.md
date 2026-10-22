# Test samples

## One Excel file, all sheets

1. Sign in and click Import data.
2. Select Sample_All_Sheets.xlsx with Auto-detect all tables.
3. Click Analyze & map fields.
4. The preview must show all 3 worksheets: Payment List (2), Inventory List (6), Bill List (2). Their order and column order are deliberately shuffled.
5. Check all 10 rows, then click Save 10 reviewed entries once.
6. Check Inventory, Bill list, Payment list and Accounts list. These sample records add billed sales 18,000 PKR, payments 6,000 PKR and outstanding 12,000 PKR.

The stock-only 20-item example supplied earlier contains only inventory; this new workbook contains all three tables.

## Handwritten register image

1. Select Handwritten_Register_20.png with Auto-detect all tables.
2. Analyze and review against the image: 10 inventory rows, 5 payments, 5 bills.
3. Bill numbers are HAND-101 through HAND-105. Their total is 41,000 PKR.
4. Payments total 15,500 PKR. Expected customer balances: Waiz 7,000; Hammad 5,000; Samad 4,500; Maaz 5,500; Saad 3,500 PKR. Total outstanding from this sample is 25,500 PKR.
5. After verifying the transcription, save the rows together. Handwriting is processed by Groq Qwen and can require correction.

These expected figures are the sample's contribution to your records. Existing records will also appear in dashboard totals. Re-imports of an identical source are blocked. Do not import alternate copies of the same data repeatedly. Both samples use amount-only bills: bills update receivables but are excluded from profit until you link their sold inventory items.
