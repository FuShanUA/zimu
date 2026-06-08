$sourcePath = "/Users/shanfu/cc/hardsubber/input.pptx"
$desktopPath = [Environment]::GetFolderPath("Desktop")
$baseName = [System.IO.Path]::GetFileNameWithoutExtension($sourcePath)
$picPptxPath = Join-Path $desktopPath "${baseName}_Picture.pptx"
$pdfPath = Join-Path $desktopPath "${baseName}_Picture.pdf"
$tempDir = Join-Path $env:TEMP "pptx_conversion_$(Get-Random)"

Write-Host "Source: $sourcePath"
Write-Host "Temp Dir: $tempDir"

# Create Temp Dir
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

$ppApp = New-Object -ComObject PowerPoint.Application
$ppApp.Visible = [Microsoft.Office.Core.MsoTriState]::msoTrue

# 1. Open Source and Export Images
Write-Host "Opening source..."
$pres = $ppApp.Presentations.Open($sourcePath, [Microsoft.Office.Core.MsoTriState]::msoTrue, [Microsoft.Office.Core.MsoTriState]::msoFalse, [Microsoft.Office.Core.MsoTriState]::msoFalse)

Write-Host "Exporting slides to JPG..."
# SaveAs method for images usually exports all slides if folder path is given, or distinct method
# Better: Iterate and Export
$slideCount = $pres.Slides.Count
For ($i = 1; $i -le $slideCount; $i++) {
    $slide = $pres.Slides.Item($i)
    $imagePath = Join-Path $tempDir "Slide_$($i.ToString('0000')).jpg"
    # Export params: Path, FilterName, ScaleWidth, ScaleHeight
    # 0,0 uses default resolution (usually 96dpi or slide size).
    # Requesting a decent resolution: 1920 width
    $slide.Export($imagePath, "JPG", 1920, 1080)
}
$pres.Close()

# 2. Create New Picture Presentation
Write-Host "Creating Picture PPTX..."
$newPres = $ppApp.Presentations.Add([Microsoft.Office.Core.MsoTriState]::msoTrue)

# Set slide size to match 16:9 (OnScreen16x9) or Custom
# A4 is common for PDF but PPTX usually 16:9. Let's assume 16:9 1920x1080 logic
$newPres.PageSetup.SlideSize = [Microsoft.Office.Interop.PowerPoint.PpSlideSizeType]::ppSlideSizeOnScreen16x9

$images = Get-ChildItem $tempDir -Filter "*.jpg" | Sort-Object Name

ForEach ($img in $images) {
    # Add Blank Slide (Layout 12 is Blank)
    $slides = $newPres.Slides
    $slideLayout = $newPres.SlideMaster.CustomLayouts.Item(7) # 7 is often Blank in default template, but safer to use just add and set layout
    # simpler: Add(Index, LayoutEnum)
    # ppLayoutBlank = 12
    $newSlide = $slides.Add($slides.Count + 1, 12) 
    
    # Clean shapes (if master has them)
    # $newSlide.Shapes.SelectAll()
    # $ppApp.ActiveWindow.Selection.ShapeRange.Delete()
    
    # Insert Image
    # AddPicture(FileName, LinkToFile, SaveWithDocument, Left, Top, Width, Height)
    $shape = $newSlide.Shapes.AddPicture($img.FullName, [Microsoft.Office.Core.MsoTriState]::msoFalse, [Microsoft.Office.Core.MsoTriState]::msoTrue, 0, 0, $newPres.PageSetup.SlideWidth, $newPres.PageSetup.SlideHeight)
}

# 3. Save as PPTX
Write-Host "Saving Picture PPTX to $picPptxPath"
$newPres.SaveAs($picPptxPath)

# 4. Save as PDF
Write-Host "Saving PDF to $pdfPath"
# ppSaveAsPDF = 32
$newPres.SaveAs($pdfPath, 32)

$newPres.Close()
$ppApp.Quit()

# Cleanup
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($ppApp) | Out-Null
Remove-Item -Recurse -Force $tempDir

Write-Host "Done."