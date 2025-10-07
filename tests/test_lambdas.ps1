# Complete Lambda test script for CFD Optimization Agent
# Tests all three Lambda functions with realistic payloads

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "CFD Optimization Agent - Lambda Tests" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Test 1: Generate Geometry
Write-Host "Test 1: Generate Geometry" -ForegroundColor Green
Write-Host "-------------------------" -ForegroundColor Green

$json1 = @"
{"parameters": {"thickness": 0.12, "max_camber": 0.04, "camber_position": 0.4, "alpha": 2.0}}
"@

$json1 | Out-File -FilePath "temp_payload.json" -Encoding ASCII -NoNewline
aws lambda invoke --function-name cfd-generate-geometry --cli-binary-format raw-in-base64-out --payload file://temp_payload.json response_geometry.json
Write-Host "Response:" -ForegroundColor Yellow
Get-Content response_geometry.json
Write-Host ""

# Test 2: Run CFD
Write-Host "Test 2: Run CFD Simulation" -ForegroundColor Green
Write-Host "-------------------------" -ForegroundColor Green

$json2 = @"
{"geometry_id": "NACA4412_a2.0", "reynolds": 500000}
"@

$json2 | Out-File -FilePath "temp_payload.json" -Encoding ASCII -NoNewline
aws lambda invoke --function-name cfd-run-cfd --cli-binary-format raw-in-base64-out --payload file://temp_payload.json response_cfd.json
Write-Host "Response:" -ForegroundColor Yellow
Get-Content response_cfd.json
Write-Host ""

# Test 3: Get Next Candidates
Write-Host "Test 3: Get Next Candidates" -ForegroundColor Green
Write-Host "-------------------------" -ForegroundColor Green

$json3 = @"
{"current_best_cd": 0.0142, "constraint_cl_min": 0.30, "iteration_number": 3}
"@

$json3 | Out-File -FilePath "temp_payload.json" -Encoding ASCII -NoNewline
aws lambda invoke --function-name cfd-get-next-candidates --cli-binary-format raw-in-base64-out --payload file://temp_payload.json response_candidates.json
Write-Host "Response:" -ForegroundColor Yellow
Get-Content response_candidates.json
Write-Host ""

# Cleanup temp file
Remove-Item temp_payload.json -ErrorAction SilentlyContinue

# Summary
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "All Lambda tests complete!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$allPassed = (Test-Path response_geometry.json) -and (Test-Path response_cfd.json) -and (Test-Path response_candidates.json)

if ($allPassed) {
    Write-Host "`nSUCCESS: All 3 Lambda functions tested!" -ForegroundColor Green
    Write-Host "Response files saved: response_*.json`n" -ForegroundColor Gray
} else {
    Write-Host "`nERROR: Some tests failed." -ForegroundColor Red
}