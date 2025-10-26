'use client';

import { useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import * as XLSX from 'xlsx-js-style';

interface GroupedJob {
  job_id: string;
  file_count: number;
  files: Array<{
    filename: string;
    size: number | null;
    content_type: string;
  }>;
}

interface UploadResponse {
  success: boolean;
  message: string;
  summary: {
    total_files: number;
    total_jobs: number;
    jobs: GroupedJob[];
  };
}

interface ClassifiedFile {
  original_filename: string;
  saved_filename: string;
  saved_path: string;
  document_type: string;
  extracted_data: Record<string, unknown> | null;
}

interface ValidationResult {
  check_id: string;
  auditing_criteria: string;
  status: 'PASS' | 'FAIL' | 'QUESTIONABLE';
  assessment: string;
  source_document: string;
  target_document: string;
  source_value: string;  // Gemini formats complex values as strings
  target_value: string;  // Gemini formats complex values as strings
}

interface TariffLineValidation {
  line_number: number;
  description: string;
  extracted_tariff_code: string;
  extracted_stat_code: string;
  suggested_tariff_code: string;
  suggested_stat_code: string;
  status: 'PASS' | 'FAIL' | 'QUESTIONABLE';
  assessment: string;
  other_suggested_codes: string[];
}

interface ProcessedJob {
  job_id: string;
  job_folder: string;
  file_count: number;
  classified_files: ClassifiedFile[];
  validation_results: {
    header: ValidationResult[];
    valuation: ValidationResult[];
    tariff_line_checks?: TariffLineValidation[];
    summary: {
      total: number;
      passed: number;
      failed: number;
      questionable: number;
    };
    tariff_summary?: {
      total: number;
      passed: number;
      failed: number;
      questionable: number;
    };
  } | null;
  validation_file: string | null;
}

interface ProcessResponse {
  success: boolean;
  message: string;
  run_id: string;
  run_path: string;
  total_files: number;
  total_jobs: number;
  jobs: ProcessedJob[];
}

export default function Home() {
  const [files, setFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [processResult, setProcessResult] = useState<ProcessResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [region, setRegion] = useState<'AU' | 'NZ'>('AU');

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const droppedFiles = Array.from(e.dataTransfer.files).filter(
      file => file.type === 'application/pdf'
    );

    if (droppedFiles.length > 0) {
      setFiles(prev => [...prev, ...droppedFiles]);
      setError(null);
    } else {
      setError('Please upload only PDF files');
    }
  }, []);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const selectedFiles = Array.from(e.target.files).filter(
        file => file.type === 'application/pdf'
      );
      
      if (selectedFiles.length > 0) {
        setFiles(prev => [...prev, ...selectedFiles]);
        setError(null);
      } else {
        setError('Please upload only PDF files');
      }
    }
  }, []);

  const removeFile = (index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleUpload = async () => {
    if (files.length === 0) {
      setError('Please select at least one PDF file');
      return;
    }

    setUploading(true);
    setError(null);
    setResult(null);
    setProcessResult(null);

    try {
      const formData = new FormData();
      files.forEach(file => {
        formData.append('files', file);
      });

      const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${endpoint}/api/upload-batch`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Upload failed');
      }

      const data: UploadResponse = await response.json();
      setResult(data);
      console.log('Upload successful:', data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
      console.error('Upload error:', err);
    } finally {
      setUploading(false);
    }
  };

  const handleProcessBatch = async () => {
    if (files.length === 0) {
      setError('Please select at least one PDF file');
      return;
    }

    setProcessing(true);
    setError(null);
    setResult(null);
    setProcessResult(null);

    try {
      const formData = new FormData();
      files.forEach(file => {
        formData.append('files', file);
      });

      const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${endpoint}/api/process-batch?region=${region}`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Processing failed');
      }

      const data: ProcessResponse = await response.json();
      setProcessResult(data);
      console.log('Processing successful:', data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Processing failed');
      console.error('Processing error:', err);
    } finally {
      setProcessing(false);
    }
  };

  const clearAll = () => {
    setFiles([]);
    setResult(null);
    setProcessResult(null);
    setError(null);
  };

  const exportToExcel = () => {
    if (!processResult) return;

    const workbook = XLSX.utils.book_new();

    processResult.jobs.forEach((job) => {
      if (!job.validation_results) return;

      const sheetData: (string | number)[][] = [];

      // Add summary section
      sheetData.push(['VALIDATION SUMMARY']);
      sheetData.push(['Job ID', job.job_id]);
      sheetData.push(['Total Checks', job.validation_results.summary.total]);
      sheetData.push(['Passed', job.validation_results.summary.passed]);
      sheetData.push(['Failed', job.validation_results.summary.failed]);
      sheetData.push(['Questionable', job.validation_results.summary.questionable]);
      sheetData.push([]);

      // Add header checks section
      if (job.validation_results.header.length > 0) {
        sheetData.push(['HEADER CHECKS']);
        sheetData.push([
          'Criteria',
          'Status',
          'Assessment',
          'Source Document',
          'Target Document',
          'Source Value',
          'Target Value',
        ]);

        job.validation_results.header.forEach((check) => {
          sheetData.push([
            check.auditing_criteria,
            check.status,
            check.assessment,
            check.source_document,
            check.target_document,
            check.source_value,
            check.target_value,
          ]);
        });

        sheetData.push([]);
      }

      // Add valuation checks section
      if (job.validation_results.valuation.length > 0) {
        sheetData.push(['VALUATION CHECKS']);
        sheetData.push([
          'Criteria',
          'Status',
          'Assessment',
          'Source Document',
          'Target Document',
          'Source Value',
          'Target Value',
        ]);

        job.validation_results.valuation.forEach((check) => {
          sheetData.push([
            check.auditing_criteria,
            check.status,
            check.assessment,
            check.source_document,
            check.target_document,
            check.source_value,
            check.target_value,
          ]);
        });
        
        sheetData.push([]);
      }

      // Add tariff line checks section if available
      if (job.validation_results.tariff_line_checks && job.validation_results.tariff_line_checks.length > 0) {
        sheetData.push(['TARIFF LINE CHECKS']);
        if (job.validation_results.tariff_summary) {
          sheetData.push(['Summary:', `Total: ${job.validation_results.tariff_summary.total}, Passed: ${job.validation_results.tariff_summary.passed}, Failed: ${job.validation_results.tariff_summary.failed}, Questionable: ${job.validation_results.tariff_summary.questionable}`]);
        }
        sheetData.push([
          'Line #',
          'Description',
          'Status',
          'Declared Code',
          'Declared Stat',
          'Recommended Code',
          'Recommended Stat',
          'Other Recommended Codes',
          'Assessment',
        ]);

        job.validation_results.tariff_line_checks.forEach((check) => {
          sheetData.push([
            check.line_number,
            check.description,
            check.status,
            check.extracted_tariff_code,
            check.extracted_stat_code,
            check.suggested_tariff_code,
            check.suggested_stat_code,
            check.other_suggested_codes.join(', '),
            check.assessment,
          ]);
        });
      }

      // Create sheet for this job
      const worksheet = XLSX.utils.aoa_to_sheet(sheetData);

      // Set column widths for better readability (handles both header/valuation and tariff formats)
      worksheet['!cols'] = [
        { wch: 50 }, // Criteria / Line # / Description
        { wch: 12 }, // Status (both formats)
        { wch: 50 }, // Assessment / Declared Code
        { wch: 15 }, // Source Document / Declared Stat
        { wch: 15 }, // Target Document / Recommended Code
        { wch: 15 }, // Source Value / Recommended Stat
        { wch: 30 }, // Target Value / Other Codes
        { wch: 50 }, // (tariff only) Assessment
      ];

      // Apply styling to cells
      const range = XLSX.utils.decode_range(worksheet['!ref'] || 'A1');
      const rowHeights: { [key: number]: number } = {};
      
      for (let rowNum = range.s.r; rowNum <= range.e.r; rowNum++) {
        for (let colNum = range.s.c; colNum <= range.e.c; colNum++) {
          const cellAddress = XLSX.utils.encode_cell({ r: rowNum, c: colNum });
          const cell = worksheet[cellAddress];
          
          if (!cell) continue;

          // Initialize cell style if not exists
          if (!cell.s) cell.s = {};

          // Color code status cells (column B - index 1)
          if (colNum === 1 && cell.v) {
            const status = String(cell.v).toUpperCase();
            if (status === 'PASS') {
              cell.s = {
                fill: { fgColor: { rgb: "92D050" } }, // Green
                font: { bold: true, color: { rgb: "FFFFFF" } }
              };
            } else if (status === 'FAIL') {
              cell.s = {
                fill: { fgColor: { rgb: "FF0000" } }, // Red
                font: { bold: true, color: { rgb: "FFFFFF" } }
              };
            } else if (status === 'QUESTIONABLE') {
              cell.s = {
                fill: { fgColor: { rgb: "FFFF00" } }, // Yellow
                font: { bold: true, color: { rgb: "000000" } }
              };
            }
          }

          // Make assessment cells wrap text (column C for header/valuation, column H for tariff)
          if ((colNum === 2 || colNum === 7) && cell.v && String(cell.v).length > 50) {
            cell.s = {
              ...cell.s,
              alignment: { wrapText: true, vertical: 'top' }
            };
            // Set row height for assessment rows (approximately 3 lines, taller for tariff)
            rowHeights[rowNum] = colNum === 7 ? 60 : 45;
          }
        }
      }

      // Apply row heights
      if (Object.keys(rowHeights).length > 0) {
        worksheet['!rows'] = [];
        for (let i = 0; i <= range.e.r; i++) {
          worksheet['!rows'][i] = rowHeights[i] ? { hpt: rowHeights[i] } : {};
        }
      }

      // Add the sheet with job ID as name
      const sheetName = `Job_${job.job_id}`.substring(0, 31); // Excel sheet name limit is 31 chars
      XLSX.utils.book_append_sheet(workbook, worksheet, sheetName);
    });

    // Generate filename with timestamp
    const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
    const filename = `audit_results_${processResult.run_id}_${timestamp}.xlsx`;

    // Write file
    XLSX.writeFile(workbook, filename);
  };

  return (
    <div className="h-screen bg-background flex flex-col p-4">
      <div className="max-w-7xl mx-auto w-full flex flex-col h-full">
        <header className="mb-4 shrink-0">
          <div className="flex items-center justify-between">
            <h1 className="text-3xl font-semibold tracking-tight">
              Clear.ai Audit
            </h1>
            <nav className="flex gap-2">
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => window.location.href = '/output'}
              >
                Browse Output
              </Button>
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => window.location.href = '/checklist'}
              >
                Manage Checklists
              </Button>
            </nav>
          </div>
        </header>

        <div className="grid grid-cols-3 gap-6 flex-1 overflow-hidden">
          {/* Left Column - Input & Files (1/3) */}
          <div className="col-span-1 space-y-4 pr-2">
            <Card>
              <CardHeader>
                <CardTitle>Upload Documents</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Dropzone */}
                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  className={`
                    border-2 border-dashed rounded-lg p-8 text-center transition-colors
                    ${isDragging 
                      ? 'border-primary bg-accent' 
                      : 'border-border hover:border-foreground/50'
                    }
                  `}
                >
                  <p className="text-sm font-medium mb-2">
                    Drop PDF files here
                  </p>                  
                  <input
                    type="file"
                    multiple
                    accept=".pdf"
                    onChange={handleFileInput}
                    className="hidden"
                    id="file-input"
                  />
                  <label htmlFor="file-input">
                    <Button asChild variant="outline" size="sm">
                      <span>Select Files</span>
                    </Button>
                  </label>
                </div>

                {/* Region Selector */}
                {files.length > 0 && (
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Region</label>
                    <select 
                      value={region} 
                      onChange={(e) => setRegion(e.target.value as 'AU' | 'NZ')}
                      className="w-full p-2 border rounded-md text-sm"
                    >
                      <option value="AU">Australia (AU)</option>
                      <option value="NZ">New Zealand (NZ)</option>
                    </select>
                  </div>
                )}

                {/* Action Buttons */}
                {files.length > 0 && (
                  <div className="space-y-2">
                    <Button
                      onClick={handleUpload}
                      disabled={uploading || processing}
                      variant="outline"
                      className="w-full"
                      size="sm"
                    >
                      {uploading ? 'Grouping...' : 'Group Files'}
                    </Button>
                    
                    <Button
                      onClick={handleProcessBatch}
                      disabled={uploading || processing}
                      className="w-full"
                      size="sm"
                    >
                      {processing ? 'Processing...' : 'Audit'}
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* File List */}
            {files.length > 0 && (
              <Card>
                <CardHeader className="pb-0">
                  <div className="flex justify-between items-center">
                    <CardTitle className="text-base">
                      Selected Files
                    </CardTitle>
                    <Badge variant="secondary">
                      {files.length}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 max-h-[calc(100vh-32rem)] overflow-y-auto">
                    {files.map((file, index) => (
                      <div
                        key={index}
                        className="flex items-start justify-between p-2 rounded-md bg-muted/50 text-xs"
                      >
                        <div className="flex-1 min-w-0 pr-2">
                          <p className="font-medium truncate">
                            {file.name}
                          </p>
                          <p className="text-muted-foreground">
                            {(file.size / 1024 / 1024).toFixed(2)} MB
                          </p>
                        </div>
                        <Button
                          onClick={() => removeFile(index)}
                          variant="ghost"
                          size="sm"
                          className="h-6 px-2"
                        >
                          Remove
                        </Button>
                      </div>
                    ))}
                  </div>
                  <Button
                    onClick={clearAll}
                    variant="ghost"
                    size="sm"
                    className="w-full mt-3"
                  >
                    Clear All
                  </Button>
                </CardContent>
              </Card>
            )}

            {/* Error Message */}
            {error && (
              <Card className="border-destructive">
                <CardContent className="pt-6">
                  <p className="text-sm text-destructive">{error}</p>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Right Column - Results (2/3) */}
          <div className="col-span-2 space-y-4 overflow-y-auto pr-2">
            {!result && !processResult && (
              <Card>
                <CardContent className="pt-6 pb-32 text-center">
                  <p className="text-sm text-muted-foreground">
                    Upload and process files to see results here
                  </p>
                </CardContent>
              </Card>
            )}

            {/* Grouping Results */}
            {result && (
              <Card>
                <CardHeader>
                  <CardTitle>Grouping Results</CardTitle>
                  <CardDescription>
                    {result.summary.total_jobs} jobs · {result.summary.total_files} files
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {result.summary.jobs.map((job, index) => (
                    <Card key={index}>
                      <CardHeader className="pb-0">
                        <div className="flex items-center justify-between">
                          <CardTitle className="text-base">
                            Job {job.job_id}
                          </CardTitle>
                          <Badge variant="secondary">
                            {job.file_count} files
                          </Badge>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <ul className="space-y-1 text-sm text-muted-foreground">
                          {job.files.map((file, fileIndex) => (
                            <li key={fileIndex}>
                              {file.filename}
                            </li>
                          ))}
                        </ul>
                      </CardContent>
                    </Card>
                  ))}
                </CardContent>
              </Card>
            )}

            {/* Processing Results with Classification */}
            {processResult && (
              <Card>
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div>
                      <CardTitle>Processing Results</CardTitle>
                      <CardDescription>
                        Run ID: {processResult.run_id} · {processResult.total_files} files processed
                      </CardDescription>
                    </div>
                    {processResult.jobs.some(job => job.validation_results) && (
                      <Button 
                        onClick={exportToExcel}
                        variant="outline"
                        size="sm"
                      >
                        Export to Excel
                      </Button>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="text-xs text-muted-foreground">
                    <span className="font-medium">Output Path:</span>{' '}
                    <code className="text-foreground break-all">{processResult.run_path}</code>
                  </div>
                  
                  <Separator />
                  
                  <div className="space-y-3">
                    {processResult.jobs.map((job, index) => (
                      <Card key={index}>
                        <CardHeader className="pb-0">
                          <div className="flex items-center justify-between">
                            <CardTitle className="text-base">
                              Job {job.job_id}
                            </CardTitle>
                            <Badge variant="secondary">
                              {job.file_count} files
                            </Badge>
                          </div>
                        </CardHeader>
                        <CardContent className="space-y-3">
                          {job.classified_files.map((file, fileIndex) => (
                            <div key={fileIndex} className="space-y-2 pb-3 border-b last:border-0 last:pb-0">
                              <div>
                                <p className="text-sm font-medium">
                                  {file.original_filename}
                                </p>
                                <p className="text-xs text-muted-foreground mt-1">
                                  {file.saved_filename}
                                </p>
                              </div>
                              
                              <div className="flex items-center gap-2">
                                <Badge variant="outline">
                                  {file.document_type.replace('_', ' ')}
                                </Badge>
                                {file.extracted_data && (
                                  <Badge variant="secondary">
                                    Data Extracted
                                  </Badge>
                                )}
                              </div>
                              
                              {file.extracted_data && (
                                <details className="mt-2">
                                  <summary className="text-xs font-medium cursor-pointer hover:underline">
                                    View extracted data ({Object.keys(file.extracted_data).length} fields)
                                  </summary>
                                  <pre className="mt-2 p-3 bg-muted rounded-md text-xs overflow-x-auto max-h-60">
                                    {JSON.stringify(file.extracted_data, null, 2)}
                                  </pre>
                                </details>
                              )}
                            </div>
                          ))}
                          
                          {/* Validation Results */}
                          {job.validation_results && (
                            <div className="pt-3 border-t space-y-3">
                              <div className="flex items-center justify-between">
                                <h4 className="text-sm font-semibold">Checklist Validation</h4>
                                <div className="flex gap-2">
                                  <Badge variant="default" className="bg-green-600">
                                    {job.validation_results.summary.passed} PASS
                                  </Badge>
                                  <Badge variant="destructive">
                                    {job.validation_results.summary.failed} FAIL
                                  </Badge>
                                  <Badge variant="outline">
                                    {job.validation_results.summary.questionable} ?
                                  </Badge>
                                </div>
                              </div>
                              
                              <details>
                                <summary className="text-xs font-medium cursor-pointer hover:underline">
                                  View validation details ({job.validation_results.summary.total} checks)
                                </summary>
                                <div className="mt-2 space-y-2">
                                  {/* Header Checks */}
                                  <div>
                                    <h5 className="text-xs font-semibold mb-1">Header Checks ({job.validation_results.header.length})</h5>
                                    <div className="space-y-1">
                                      {job.validation_results.header.map((check, i) => (
                                        <div key={i} className="text-xs p-2 bg-muted rounded">
                                          <div className="flex items-center justify-between mb-1">
                                            <span className="font-medium">{check.auditing_criteria}</span>
                                            <Badge 
                                              variant={check.status === 'PASS' ? 'default' : check.status === 'FAIL' ? 'destructive' : 'outline'}
                                              className={check.status === 'PASS' ? 'bg-green-600' : ''}
                                            >
                                              {check.status}
                                            </Badge>
                                          </div>
                                          <p className="text-muted-foreground">{check.assessment}</p>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                  
                                  {/* Valuation Checks */}
                                  <div>
                                    <h5 className="text-xs font-semibold mb-1">Valuation Checks ({job.validation_results.valuation.length})</h5>
                                    <div className="space-y-1">
                                      {job.validation_results.valuation.map((check, i) => (
                                        <div key={i} className="text-xs p-2 bg-muted rounded">
                                          <div className="flex items-center justify-between mb-1">
                                            <span className="font-medium">{check.auditing_criteria}</span>
                                            <Badge 
                                              variant={check.status === 'PASS' ? 'default' : check.status === 'FAIL' ? 'destructive' : 'outline'}
                                              className={check.status === 'PASS' ? 'bg-green-600' : ''}
                                            >
                                              {check.status}
                                            </Badge>
                                          </div>
                                          <p className="text-muted-foreground">{check.assessment}</p>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                </div>
                              </details>
                            </div>
                          )}
                          
                          <div className="pt-3 border-t">
                            <p className="text-xs text-muted-foreground">
                              <span className="font-medium">Job folder:</span>{' '}
                              <code>{job.job_folder}</code>
                            </p>
                            {job.validation_file && (
                              <p className="text-xs text-muted-foreground mt-1">
                                <span className="font-medium">Validation file:</span>{' '}
                                <code>{job.validation_file.split('/').pop()}</code>
                              </p>
                            )}
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
