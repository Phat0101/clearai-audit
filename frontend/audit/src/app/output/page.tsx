'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { 
  ChevronRight, 
  ChevronDown, 
  Folder, 
  File, 
  Download, 
  Trash2,
  Home,
  RefreshCw,
  Calendar,
  HardDrive,
  FileSpreadsheet
} from 'lucide-react';
import * as XLSX from 'xlsx-js-style';

interface FileItem {
  name: string;
  path: string;
  size: number;
  type: 'file' | 'directory';
  modified: number;
}

interface Run {
  name: string;
  path: string;
  modified: number;
  size: number;
}

interface ExpandedDirectories {
  [key: string]: FileItem[] | null | 'collapsed'; // null means loading, 'collapsed' means not expanded
}

interface ValidationResult {
  check_id: string;
  auditing_criteria: string;
  status: 'PASS' | 'FAIL' | 'QUESTIONABLE' | 'N/A';
  assessment: string;
  source_document: string;
  target_document: string;
  source_value: string;
  target_value: string;
}

interface TariffLineValidation {
  line_number: number;
  description: string;
  // Tariff Classification Check
  extracted_tariff_code: string;
  extracted_stat_code: string;
  suggested_tariff_code: string;
  suggested_stat_code: string;
  tariff_classification_status: 'PASS' | 'FAIL' | 'QUESTIONABLE' | 'N/A';
  tariff_classification_assessment: string;
  other_suggested_codes: string[];
  // Concession Check
  claimed_concession: string | null;
  concession_status: 'PASS' | 'FAIL' | 'QUESTIONABLE' | 'N/A';
  concession_assessment: string;
  concession_link: string | null;
  // Quantity Check
  invoice_quantity: string;
  entry_print_quantity: string;
  quantity_status: 'PASS' | 'FAIL' | 'QUESTIONABLE' | 'N/A';
  quantity_assessment: string;
  // GST Exemption Check
  gst_exemption_claimed: boolean;
  gst_exemption_status: 'PASS' | 'FAIL' | 'QUESTIONABLE' | 'N/A';
  gst_exemption_assessment: string;
  // Overall Status
  overall_status: 'PASS' | 'FAIL' | 'QUESTIONABLE' | 'N/A';
}

interface ValidationData {
  header: ValidationResult[];
  valuation: ValidationResult[];
  tariff_line_checks?: TariffLineValidation[];
  summary: {
    total: number;
    passed: number;
    failed: number;
    questionable: number;
    not_applicable?: number;
  };
  tariff_summary?: {
    total: number;
    passed: number;
    failed: number;
    questionable: number;
    not_applicable?: number;
  };
}

export default function OutputPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<Run[]>([]);
  const [expandedDirs, setExpandedDirs] = useState<ExpandedDirectories>({});
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  const fetchRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/output/runs`);
      if (!response.ok) throw new Error('Failed to fetch runs');
      const data = await response.json();
      setRuns(data.runs || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load runs');
    } finally {
      setLoading(false);
    }
  }, [API_URL]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  const loadDirectory = async (path: string) => {
    // Set loading state
    setExpandedDirs(prev => ({ ...prev, [path]: null }));
    
    try {
      const response = await fetch(`${API_URL}/api/output/browse?path=${encodeURIComponent(path)}`);
      if (!response.ok) throw new Error('Failed to load directory');
      const data = await response.json();
      
      setExpandedDirs(prev => ({ ...prev, [path]: data.items }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load directory');
      setExpandedDirs(prev => ({ ...prev, [path]: 'collapsed' }));
    }
  };

  const toggleDirectory = (path: string) => {
    const currentState = expandedDirs[path];
    
    if (!currentState || currentState === 'collapsed') {
      // Not loaded yet or collapsed, load it
      loadDirectory(path);
    } else {
      // Already loaded or loading, collapse it
      setExpandedDirs(prev => {
        const newState = { ...prev };
        newState[path] = 'collapsed';
        // Also collapse all subdirectories
        Object.keys(newState).forEach(key => {
          if (key.startsWith(path + '/')) {
            newState[key] = 'collapsed';
          }
        });
        return newState;
      });
    }
  };

  const downloadFile = async (path: string, filename: string) => {
    try {
      const response = await fetch(`${API_URL}/api/output/download?path=${encodeURIComponent(path)}`);
      if (!response.ok) throw new Error('Failed to download file');
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to download file');
    }
  };

  const deleteItem = async (path: string) => {
    if (!confirm(`Are you sure you want to delete ${path}?`)) return;
    
    try {
      const response = await fetch(`${API_URL}/api/output/delete?path=${encodeURIComponent(path)}`, {
        method: 'DELETE'
      });
      if (!response.ok) throw new Error('Failed to delete item');
      
      // Refresh the runs list
      await fetchRuns();
      // Clear expanded directories to force reload
      setExpandedDirs({});
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete item');
    }
  };

  const exportRunToExcel = async (runPath: string, runName: string) => {
    setExporting(true);
    setError(null);
    try {
      // First, get the list of files in the run directory
      const response = await fetch(`${API_URL}/api/output/browse?path=${encodeURIComponent(runPath)}`);
      if (!response.ok) throw new Error('Failed to load run contents');
      const data = await response.json();
      
      // Find all validation JSON files
      const validationFiles = data.items.filter((item: FileItem) => 
        item.type === 'file' && 
        item.name.includes('validation') && 
        item.name.endsWith('.json')
      );

      if (validationFiles.length === 0) {
        setError('No validation results found in this run');
        return;
      }

      const workbook = XLSX.utils.book_new();

      // Fetch and process each validation file
      for (const file of validationFiles) {
        try {
          // Download the validation file
          const fileResponse = await fetch(`${API_URL}/api/output/download?path=${encodeURIComponent(file.path)}`);
          if (!fileResponse.ok) continue;
          
          const validationData: ValidationData = await fileResponse.json();
          
          // Extract job ID from filename (e.g., "job_2219477116_validation_AU.json" -> "2219477116")
          const jobIdMatch = file.name.match(/job_(\d+)_validation/);
          const jobId = jobIdMatch ? jobIdMatch[1] : file.name.replace('.json', '');

          const sheetData: (string | number)[][] = [];

          // Add summary section
          sheetData.push(['Job ID', jobId]);
          // sheetData.push(['Total Checks', validationData.summary.total]);
          // sheetData.push(['Passed', validationData.summary.passed]);
          // sheetData.push(['Failed', validationData.summary.failed]);
          // sheetData.push(['Questionable', validationData.summary.questionable]);
          // if (validationData.summary.not_applicable) {
          //   sheetData.push(['N/A', validationData.summary.not_applicable]);
          // }
          sheetData.push([]);

          // Add header checks section
          if (validationData.header && validationData.header.length > 0) {
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

            validationData.header.forEach((check) => {
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
          if (validationData.valuation && validationData.valuation.length > 0) {
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

            validationData.valuation.forEach((check) => {
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

          // Add Line Data section if available
          if (validationData.tariff_line_checks && validationData.tariff_line_checks.length > 0) {
            sheetData.push([]);
            sheetData.push(['Line Data']);
            sheetData.push([]);
            
            // Add each line with its 4 checks
            validationData.tariff_line_checks.forEach((line) => {
              // Line header
              sheetData.push([`Line ${line.line_number}`]);
              sheetData.push([
                'Auditing Criteria',
                'Results',
                'Comments'
              ]);
              
              // Check 1: Tariff Classification & Stat code
              sheetData.push([
                'Tariff Classification & Stat code',
                line.tariff_classification_status,
                `Declared: ${line.extracted_tariff_code}.${line.extracted_stat_code} | Suggested: ${line.suggested_tariff_code}.${line.suggested_stat_code} | ${line.tariff_classification_assessment}`
              ]);
              
              // Check 2: Tariff/Bylaw Concession
              const concessionComment = line.claimed_concession 
                ? `Claimed: ${line.claimed_concession} | ${line.concession_assessment}`
                : line.concession_assessment;
              sheetData.push([
                'Tariff/Bylaw Concession',
                line.concession_status,
                concessionComment
              ]);
              
              // Check 3: Quantity
              sheetData.push([
                'Quantity',
                line.quantity_status,
                `Invoice: ${line.invoice_quantity} | Entry: ${line.entry_print_quantity} | ${line.quantity_assessment}`
              ]);
              
              // Check 4: GST Exemption
              const gstComment = line.gst_exemption_claimed
                ? `GST exemption claimed | ${line.gst_exemption_assessment}`
                : line.gst_exemption_assessment;
              sheetData.push([
                'GST Exemption',
                line.gst_exemption_status,
                gstComment
              ]);
              
              sheetData.push([]);
            });
          }

          // Create sheet for this job
          const worksheet = XLSX.utils.aoa_to_sheet(sheetData);

          // Set column widths for better readability
          worksheet['!cols'] = [
            { wch: 45 }, // Auditing Criteria
            { wch: 15 }, // Results/Status
            { wch: 80 }, // Comments/Assessment
            { wch: 18 }, // Source Document
            { wch: 18 }, // Target Document
            { wch: 18 }, // Source Value
            { wch: 18 }, // Target Value
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
                } else if (status === 'N/A') {
                  cell.s = {
                    fill: { fgColor: { rgb: "F0F0F0" } }, // Light gray
                    font: { bold: true, color: { rgb: "666666" } }
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
          const sheetName = `Job_${jobId}`.substring(0, 31); // Excel sheet name limit is 31 chars
          XLSX.utils.book_append_sheet(workbook, worksheet, sheetName);
        } catch (err) {
          console.error(`Failed to process ${file.name}:`, err);
        }
      }

      // Check if any sheets were added
      if (workbook.SheetNames.length === 0) {
        setError('No valid validation data found');
        return;
      }

      // Generate filename with timestamp
      const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
      const filename = `audit_results_${runName}_${timestamp}.xlsx`;

      // Write file
      XLSX.writeFile(workbook, filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to export to Excel');
    } finally {
      setExporting(false);
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const formatDate = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleString();
  };

  const renderFileItem = (item: FileItem, depth: number = 0) => {
    const dirState = expandedDirs[item.path];
    const isExpanded = dirState && dirState !== 'collapsed';
    const isLoading = dirState === null;
    const isDirectory = item.type === 'directory';
    
    return (
      <div key={item.path}>
        <div 
          className={`
            flex items-center justify-between p-2 hover:bg-muted/50 rounded-md group
            ${depth > 0 ? 'ml-' + (depth * 4) : ''}
          `}
          style={{ marginLeft: `${depth * 1.5}rem` }}
        >
          <div className="flex items-center gap-2 flex-1 min-w-0">
            {isDirectory ? (
              <button
                onClick={() => toggleDirectory(item.path)}
                className="flex items-center gap-2 flex-1 min-w-0 text-left hover:underline"
              >
                {isLoading ? (
                  <RefreshCw className="h-4 w-4 animate-spin text-muted-foreground" />
                ) : isExpanded ? (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                )}
                <Folder className="h-4 w-4 text-blue-500 shrink-0" />
                <span className="text-sm font-medium truncate">{item.name}</span>
              </button>
            ) : (
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <File className="h-4 w-4 text-muted-foreground shrink-0 ml-6" />
                <span className="text-sm truncate">{item.name}</span>
              </div>
            )}
          </div>
          
          <div className="flex items-center gap-2">
            {!isDirectory && (
              <>
                <span className="text-xs text-muted-foreground">
                  {formatBytes(item.size)}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 opacity-0 group-hover:opacity-100"
                  onClick={() => downloadFile(item.path, item.name)}
                >
                  <Download className="h-3 w-3" />
                </Button>
              </>
            )}
            {isDirectory && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 opacity-0 group-hover:opacity-100 text-destructive hover:text-destructive"
                onClick={() => deleteItem(item.path)}
              >
                <Trash2 className="h-3 w-3" />
              </Button>
            )}
          </div>
        </div>
        
        {/* Render subdirectory contents */}
        {isDirectory && isExpanded && !isLoading && expandedDirs[item.path] && (
          <div>
            {(expandedDirs[item.path] as FileItem[]).map(subItem => 
              renderFileItem(subItem, depth + 1)
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-background p-4 relative">
      {/* Loading Overlay for Excel Export */}
      {exporting && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center">
          <Card className="w-96">
            <CardContent className="pt-6 pb-6">
              <div className="flex flex-col items-center gap-4">
                <div className="relative">
                  <div className="h-16 w-16 rounded-full border-4 border-primary/20"></div>
                  <div className="absolute top-0 left-0 h-16 w-16 rounded-full border-4 border-primary border-t-transparent animate-spin"></div>
                </div>
                <div className="text-center">
                  <h3 className="text-lg font-semibold mb-2">Exporting to Excel</h3>
                  <p className="text-sm text-muted-foreground mb-4">
                    Please wait while we generate your file...
                  </p>
                  <p className="text-xs text-muted-foreground">
                    This may take a moment for large runs
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
      
      <div className="max-w-7xl mx-auto">
        <header className="mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-semibold tracking-tight">
                Output Browser
              </h1>
              <p className="text-sm text-muted-foreground mt-1">
                Browse and download audit results
              </p>
            </div>
            <div className="flex gap-2">
              <Button 
                variant="outline"
                onClick={fetchRuns}
                disabled={loading}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </Button>
              <Button 
                variant="default"
                onClick={() => router.push('/')}
              >
                <Home className="h-4 w-4 mr-2" />
                Home
              </Button>
            </div>
          </div>
        </header>

        {error && (
          <Card className="border-destructive mb-4">
            <CardContent className="pt-6">
              <p className="text-sm text-destructive">{error}</p>
            </CardContent>
          </Card>
        )}

        {loading && runs.length === 0 ? (
          <Card>
            <CardContent className="pt-6 flex items-center justify-center py-12">
              <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
            </CardContent>
          </Card>
        ) : runs.length === 0 ? (
          <Card>
            <CardContent className="pt-6 text-center py-12">
              <HardDrive className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-sm text-muted-foreground">
                No output directories found. Process some files to see results here.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {runs.map((run) => (
              <Card key={run.path}>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <CardTitle className="text-lg flex items-center gap-2">
                        <Calendar className="h-4 w-4 text-muted-foreground" />
                        {run.name}
                      </CardTitle>
                      <CardDescription className="mt-1">
                        Modified: {formatDate(run.modified)} · Size: {formatBytes(run.size)}
                      </CardDescription>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => exportRunToExcel(run.path, run.name)}
                      >
                        <FileSpreadsheet className="h-4 w-4 mr-2" />
                        Export to Excel
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => deleteItem(run.path)}
                      >
                        <Trash2 className="h-4 w-4 mr-2" />
                        Delete Run
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="border rounded-lg p-2">
                    {renderFileItem({
                      name: run.name,
                      path: run.path,
                      size: run.size,
                      type: 'directory',
                      modified: run.modified
                    }, 0)}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

