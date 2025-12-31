'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';

interface GroupedFolder {
  name: string;
  path: string;
  job_count: number;
  completed_jobs: number;
  pending_jobs: number;
  created: string;
}

interface JobStatus {
  job_id: string;
  hawb?: string;
  dhl_job_number?: string;
  broker?: string;
  status: 'completed' | 'pending' | 'failed';
  has_pdfs: boolean;
}

interface JobListResponse {
  success: boolean;
  folder_name: string;
  jobs: JobStatus[];
  total: number;
  completed: number;
  pending: number;
}

interface ListGroupedFoldersResponse {
  success: boolean;
  input_folder: string;
  folders: GroupedFolder[];
}

interface NZAuditJobResult {
  job_id: string;
  success: boolean;
  error?: string;
  job_folder?: string;  // Path to output job folder
  csv_path?: string;    // Path to individual job CSV
  extraction?: {
    audit_month: string;
    tl: string;
    broker: string;
    dhl_job_number: string;
    hawb: string;
    import_export: string;
    entry_number: string;
    entry_date: string;
  };
  header_validation?: {
    client_code_name_correct: string;
    supplier_or_cnee_correct: string;
    invoice_number_correct: string;
    vfd_correct: string;
    currency_correct: string;
    incoterm_correct: string;
    freight_zero_if_inclusive_incoterm: string;
    freight_correct: string;
    load_port_correct: string;
    relationship_indicator_correct: string;
  };
  auditor_comments?: string;
}

interface NZAuditBatchResponse {
  success: boolean;
  message: string;
  run_id?: string;      // Run identifier
  run_path?: string;    // Path to output run folder
  total_jobs: number;
  successful_jobs: number;
  failed_jobs: number;
  skipped_jobs: number; // Jobs skipped (already complete)
  csv_path?: string;    // Path to combined CSV
  csv_filename?: string;
  xlsx_path?: string;   // Path to combined XLSX (with broker sheets)
  xlsx_filename?: string;
  results: NZAuditJobResult[];
}

export default function NZAuditPage() {
  const router = useRouter();
  const [folders, setFolders] = useState<GroupedFolder[]>([]);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [auditResult, setAuditResult] = useState<NZAuditBatchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobList, setJobList] = useState<JobListResponse | null>(null);
  const [processingJob, setProcessingJob] = useState<string | null>(null);
  
  // Audit Summary Upload States
  const [summaryFile, setSummaryFile] = useState<File | null>(null);
  const [summaryMonth, setSummaryMonth] = useState('');
  const [summaryUploading, setSummaryUploading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load grouped folders on mount
  useEffect(() => {
    loadGroupedFolders();
  }, []);

  // Load job list when folder is selected
  useEffect(() => {
    if (selectedFolder) {
      loadJobList();
    } else {
      setJobList(null);
    }
  }, [selectedFolder]);

  const loadGroupedFolders = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${endpoint}/api/nz-audit/grouped-folders`);
      
      if (!response.ok) {
        throw new Error('Failed to load grouped folders');
      }
      
      const data: ListGroupedFoldersResponse = await response.json();
      setFolders(data.folders);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load folders');
    } finally {
      setLoading(false);
    }
  };

  const loadJobList = async () => {
    if (!selectedFolder) return;
    
    try {
      const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${endpoint}/api/nz-audit/jobs?folder_name=${encodeURIComponent(selectedFolder)}`);
      
      if (!response.ok) {
        throw new Error('Failed to load job list');
      }
      
      const data: JobListResponse = await response.json();
      setJobList(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load job list');
    }
  };

  const handleRunSingleJob = async (jobId: string) => {
    if (!selectedFolder) return;
    
    setProcessingJob(jobId);
    setError(null);
    
    try {
      const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(
        `${endpoint}/api/nz-audit/process-single-job?folder_name=${encodeURIComponent(selectedFolder)}&job_id=${encodeURIComponent(jobId)}&update_combined=true`,
        { method: 'POST' }
      );
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Job processing failed');
      }
      
      // Reload job list to update status
      await loadJobList();
      // Reload folders to update counts
      await loadGroupedFolders();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Job processing failed');
    } finally {
      setProcessingJob(null);
    }
  };

  const handleClearMarkers = async () => {
    if (!selectedFolder) return;
    
    if (!confirm(`This will clear all progress for ${selectedFolder} and create a new output folder. Continue?`)) {
      return;
    }
    
    try {
      const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(
        `${endpoint}/api/nz-audit/clear-markers?folder_name=${encodeURIComponent(selectedFolder)}&new_run=true`,
        { method: 'POST' }
      );
      
      if (!response.ok) {
        throw new Error('Failed to clear markers');
      }
      
      // Refresh folder list and job list to update counts
      await loadGroupedFolders();
      if (selectedFolder) {
        await loadJobList();
      }
      setAuditResult(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clear markers');
    }
  };

  const handleRunAudit = async (resumeFailedOnly: boolean = false) => {
    if (!selectedFolder) {
      setError('Please select a grouped folder');
      return;
    }

    setProcessing(true);
    setError(null);
    setAuditResult(null);

    try {
      const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const params = new URLSearchParams({
        folder_name: selectedFolder,
        resume_failed_only: resumeFailedOnly.toString()
      });
      const response = await fetch(
        `${endpoint}/api/nz-audit/process?${params}`,
        { method: 'POST' }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Audit failed');
      }

      const data: NZAuditBatchResponse = await response.json();
      setAuditResult(data);
      
      // Refresh folder list and job list to update counts
      await loadGroupedFolders();
      if (selectedFolder) {
        await loadJobList();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Audit failed');
    } finally {
      setProcessing(false);
    }
  };

  const handleDownloadCSV = () => {
    if (!auditResult?.csv_path) return;
    
    const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    window.open(`${endpoint}/api/nz-audit/download-csv?csv_path=${encodeURIComponent(auditResult.csv_path)}`, '_blank');
  };

  const handleDownloadXLSX = () => {
    if (!auditResult?.xlsx_path) return;
    
    const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    window.open(`${endpoint}/api/nz-audit/download-xlsx?xlsx_path=${encodeURIComponent(auditResult.xlsx_path)}`, '_blank');
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'Yes':
        return <Badge className="bg-green-500 text-white">Yes</Badge>;
      case 'No':
        return <Badge className="bg-red-500 text-white">No</Badge>;
      case 'N/A':
        return <Badge variant="secondary">N/A</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  // Handle summary file selection
  const handleSummaryFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (!file.name.endsWith('.xlsx') && !file.name.endsWith('.xls')) {
        setSummaryError('Please upload an Excel file (.xlsx or .xls)');
        setSummaryFile(null);
        return;
      }
      setSummaryFile(file);
      setSummaryError(null);
    }
  };

  // Handle summary upload and download
  const handleGenerateSummary = async () => {
    if (!summaryFile) {
      setSummaryError('Please select an Excel file');
      return;
    }

    setSummaryUploading(true);
    setSummaryError(null);

    try {
      const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const formData = new FormData();
      formData.append('file', summaryFile);
      formData.append('month', summaryMonth || '');

      const response = await fetch(`${endpoint}/api/nz-audit-summary/generate`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to generate summary');
      }

      const data = await response.json();
      
      // Automatically download the generated summary
      if (data.output_file) {
        window.open(
          `${endpoint}/api/nz-audit-summary/download?file_path=${encodeURIComponent(data.output_file)}`,
          '_blank'
        );
      }

      // Reset form
      setSummaryFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (err) {
      setSummaryError(err instanceof Error ? err.message : 'Failed to generate summary');
    } finally {
      setSummaryUploading(false);
    }
  };

  return (
    <div className="h-screen bg-background flex flex-col p-4 relative">
      {/* Loading Overlay */}
      {processing && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center">
          <Card className="w-96">
            <CardContent className="pt-6 pb-6">
              <div className="flex flex-col items-center gap-4">
                <div className="relative">
                  <div className="h-16 w-16 rounded-full border-4 border-primary/20"></div>
                  <div className="absolute top-0 left-0 h-16 w-16 rounded-full border-4 border-primary border-t-transparent animate-spin"></div>
                </div>
                <div className="text-center">
                  <h3 className="text-lg font-semibold mb-2">Running NZ Audit</h3>
                  <p className="text-sm text-muted-foreground mb-4">
                    Processing all jobs in the selected folder...
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Do not close or refresh this page
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      <div className="max-w-7xl mx-auto w-full flex flex-col h-full">
        <header className="mb-4 shrink-0">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-semibold tracking-tight">
                🇳🇿 NZ Audit
              </h1>
            </div>
            <nav className="flex gap-2">
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => router.push('/')}
              >
                ← Back to Main
              </Button>
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => router.push('/output')}
              >
                Browse Output
              </Button>
            </nav>
          </div>
        </header>

        <div className="grid grid-cols-3 gap-6 flex-1 overflow-hidden">
          {/* Left Column - Folder Selection */}
          <div className="col-span-1 space-y-4 pr-2">
            <Card>
              <CardHeader>
                <CardTitle>Select Grouped Folder</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Button
                  onClick={loadGroupedFolders}
                  variant="outline"
                  size="sm"
                  className="w-full"
                  disabled={loading}
                >
                  {loading ? 'Loading...' : 'Refresh Folders'}
                </Button>

                {loading ? (
                  <div className="text-center py-8 text-muted-foreground">
                    Loading folders...
                  </div>
                ) : folders.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">
                    No grouped folders found. Run &quot;Group Jobs&quot; first.
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[300px] overflow-y-auto">
                    {folders.map((folder) => (
                      <div
                        key={folder.name}
                        onClick={() => setSelectedFolder(folder.name)}
                        className={`
                          p-3 rounded-md cursor-pointer transition-colors
                          ${selectedFolder === folder.name 
                            ? 'bg-primary text-primary-foreground' 
                            : 'bg-muted/50 hover:bg-muted'
                          }
                        `}
                      >
                        <div className="flex justify-between items-center mb-1">
                          <span className="font-medium text-sm truncate">
                            {folder.name}
                          </span>
                          <Badge variant={selectedFolder === folder.name ? "secondary" : "outline"}>
                            {folder.job_count} jobs
                          </Badge>
                        </div>
                        <div className="flex justify-between items-center text-xs opacity-70">
                          <span>{new Date(folder.created).toLocaleString()}</span>
                          {folder.completed_jobs > 0 && (
                            <span className="text-green-500">
                              ✓ {folder.completed_jobs}/{folder.job_count}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {selectedFolder && (() => {
                  const folder = folders.find(f => f.name === selectedFolder);
                  const hasCompleted = folder && folder.completed_jobs > 0;
                  const hasPending = folder && folder.pending_jobs > 0;
                  
                  return (
                    <div className="space-y-2">
                      {/* Show status summary */}
                      {folder && folder.completed_jobs > 0 && (
                        <div className="p-2 bg-muted/50 rounded text-xs text-center">
                          <span className="text-green-500 font-medium">{folder.completed_jobs}</span> completed, 
                          <span className={`font-medium ${folder.pending_jobs > 0 ? ' text-orange-500' : ''}`}> {folder.pending_jobs}</span> pending
                        </div>
                      )}
                      
                      {/* Resume Failed button - show when there are completed jobs AND pending jobs */}
                      {hasCompleted && hasPending && (
                        <Button
                          onClick={() => handleRunAudit(true)}
                          disabled={processing}
                          variant="outline"
                          className="w-full border-orange-500 text-orange-600 hover:bg-orange-50"
                        >
                          {processing ? 'Resuming...' : `Resume Failed (${folder.pending_jobs} jobs)`}
                        </Button>
                      )}
                      
                      {/* Run Audit button */}
                      <Button
                        onClick={() => handleRunAudit(false)}
                        disabled={processing}
                        className="w-full"
                      >
                        {processing ? 'Running Audit...' : 'Run NZ Audit'}
                      </Button>
                      
                      {/* Reset button - only show when there's progress */}
                      {hasCompleted && (
                        <Button
                          onClick={handleClearMarkers}
                          disabled={processing}
                          variant="ghost"
                          size="sm"
                          className="w-full text-xs text-muted-foreground hover:text-destructive"
                        >
                          Reset Progress & Start New Run
                        </Button>
                      )}
                    </div>
                  );
                })()}
              </CardContent>
            </Card>

            {/* Job List */}
            {selectedFolder && jobList && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Job List</CardTitle>
                  <CardDescription>
                    {jobList.completed} completed, {jobList.pending} pending
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 max-h-[calc(100vh-580px)] overflow-y-auto">
                    {jobList.jobs.map((job) => (
                      <div
                        key={job.job_id}
                        className={`
                          p-2 rounded-md border text-sm
                          ${job.status === 'completed' 
                            ? 'bg-green-50 border-green-200' 
                            : job.status === 'failed'
                            ? 'bg-red-50 border-red-200'
                            : 'bg-muted/50 border-muted'
                          }
                        `}
                      >
                        <div className="flex justify-between items-start gap-2">
                          <div className="flex-1 min-w-0">
                            <div className="font-medium truncate">
                              {job.dhl_job_number || job.hawb || job.job_id}
                            </div>
                            {job.broker && (
                              <div className="text-xs text-muted-foreground truncate">
                                {job.broker}
                              </div>
                            )}
                            {job.hawb && job.hawb !== job.job_id && (
                              <div className="text-xs text-muted-foreground">
                                HAWB: {job.hawb}
                              </div>
                            )}
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <Badge 
                              variant={
                                job.status === 'completed' ? 'default' :
                                job.status === 'failed' ? 'destructive' :
                                'secondary'
                              }
                              className="text-xs"
                            >
                              {job.status === 'completed' ? '✓' : job.status === 'pending' ? '⏳' : '✗'}
                            </Badge>
                            {job.has_pdfs && (
                              <Button
                                onClick={() => handleRunSingleJob(job.job_id)}
                                disabled={processing || processingJob === job.job_id}
                                size="sm"
                                variant={job.status === 'completed' ? 'outline' : 'default'}
                                className={`h-7 text-xs ${job.status === 'completed' ? 'border-green-500 text-green-600 hover:bg-green-50' : ''}`}
                              >
                                {processingJob === job.job_id ? '...' : job.status === 'completed' ? 'Rerun' : 'Run'}
                              </Button>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                  
                  {/* Run Remaining button */}
                  {jobList.pending > 0 && (
                    <div className="mt-4 pt-4 border-t">
                      <Button
                        onClick={() => handleRunAudit(true)}
                        disabled={processing}
                        variant="outline"
                        className="w-full border-orange-500 text-orange-600 hover:bg-orange-50"
                      >
                        {processing ? 'Running...' : `Run Remaining (${jobList.pending} jobs)`}
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Error Display */}
            {error && (
              <Card className="border-destructive">
                <CardContent className="pt-6">
                  <p className="text-sm text-destructive">{error}</p>
                </CardContent>
              </Card>
            )}

            {/* Audit Summary Generator */}
            <Card className="border-blue-200 bg-blue-50/30">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  📊 Generate Audit Summary
                </CardTitle>
                <CardDescription>
                  Upload completed audit Excel to generate accuracy & error summary
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <label className="text-sm font-medium mb-2 block">
                    Month (optional)
                  </label>
                  <Input
                    type="text"
                    placeholder="e.g., Jul-24"
                    value={summaryMonth}
                    onChange={(e) => setSummaryMonth(e.target.value)}
                    className="bg-white"
                  />
                </div>
                
                <div>
                  <label className="text-sm font-medium mb-2 block">
                    Audited Excel File
                  </label>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".xlsx,.xls"
                    onChange={handleSummaryFileChange}
                    className="block w-full text-sm text-gray-500
                      file:mr-4 file:py-2 file:px-4
                      file:rounded-md file:border-0
                      file:text-sm file:font-semibold
                      file:bg-blue-50 file:text-blue-700
                      hover:file:bg-blue-100
                      cursor-pointer"
                  />
                  {summaryFile && (
                    <p className="text-xs text-muted-foreground mt-1">
                      Selected: {summaryFile.name}
                    </p>
                  )}
                </div>

                {summaryError && (
                  <p className="text-sm text-destructive">{summaryError}</p>
                )}

                <Button
                  onClick={handleGenerateSummary}
                  disabled={!summaryFile || summaryUploading}
                  className="w-full bg-blue-600 hover:bg-blue-700"
                >
                  {summaryUploading ? (
                    <>
                      <span className="animate-spin mr-2">⏳</span>
                      Generating...
                    </>
                  ) : (
                    <>
                      📥 Generate & Download Summary
                    </>
                  )}
                </Button>

                <p className="text-xs text-muted-foreground text-center">
                  Calculates accuracy per broker and counts errors by category
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Right Column - Results */}
          <div className="col-span-2 space-y-4 overflow-y-auto pr-2 pb-4">
            {!auditResult && !processing && (
              <Card>
                <CardContent className="pt-6 pb-32 text-center">
                  <p className="text-sm text-muted-foreground">
                    Select a grouped folder and run audit to see results here
                  </p>
                </CardContent>
              </Card>
            )}

            {/* Audit Results */}
            {auditResult && (
              <>
                {/* Summary Card */}
                <Card>
                  <CardHeader>
                    <div className="flex justify-between items-center">
                      <CardTitle>Audit Complete</CardTitle>
                      <div className="flex gap-2">
                        {auditResult.csv_path && (
                          <Button onClick={handleDownloadCSV} size="sm" variant="outline">
                            Download CSV
                          </Button>
                        )}
                        {auditResult.xlsx_path && (
                          <Button onClick={handleDownloadXLSX} size="sm">
                            Download XLSX (Broker Sheets)
                          </Button>
                        )}
                      </div>
                    </div>
                    <CardDescription>
                      {auditResult.message}
                      {auditResult.xlsx_path && (
                        <span className="block mt-1 text-xs">
                          📊 XLSX includes separate sheets per broker + summary sheet
                        </span>
                      )}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex gap-4 mb-4">
                      <div className="text-center">
                        <div className="text-2xl font-bold text-green-500">
                          {auditResult.successful_jobs}
                        </div>
                        <div className="text-xs text-muted-foreground">Successful</div>
                      </div>
                      <div className="text-center">
                        <div className="text-2xl font-bold text-red-500">
                          {auditResult.failed_jobs}
                        </div>
                        <div className="text-xs text-muted-foreground">Failed</div>
                      </div>
                      {auditResult.skipped_jobs > 0 && (
                        <div className="text-center">
                          <div className="text-2xl font-bold text-gray-400">
                            {auditResult.skipped_jobs}
                          </div>
                          <div className="text-xs text-muted-foreground">Skipped</div>
                        </div>
                      )}
                      <div className="text-center">
                        <div className="text-2xl font-bold">
                          {auditResult.total_jobs}
                        </div>
                        <div className="text-xs text-muted-foreground">Total</div>
                      </div>
                    </div>
                    
                    {/* Retry tip if there are failed jobs */}
                    {auditResult.failed_jobs > 0 && (
                      <div className="p-3 bg-orange-50 border border-orange-200 rounded-md text-xs mb-4">
                        <div className="font-semibold text-orange-700 mb-1">💡 {auditResult.failed_jobs} job(s) failed</div>
                        <div className="text-orange-600">
                          Click &quot;Resume Failed&quot; to retry only the failed jobs. Results will be merged into the same CSV.
                        </div>
                      </div>
                    )}
                    
                    {/* Output folder info */}
                    {auditResult.run_path && (
                      <div className="p-3 bg-muted/50 rounded-md text-xs">
                        <div className="font-semibold mb-1">📂 Output Location</div>
                        <div className="text-muted-foreground font-mono break-all">
                          {auditResult.run_path}
                        </div>
                        {auditResult.run_id && (
                          <div className="mt-1">
                            <span className="text-muted-foreground">Run ID:</span>{' '}
                            <span className="font-medium">{auditResult.run_id}</span>
                          </div>
                        )}
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Individual Job Results */}
                {auditResult.results.map((job, index) => (
                  <Card key={index}>
                    <CardHeader className="pb-2">
                      <div className="flex justify-between items-center">
                        <CardTitle className="text-lg">
                          Job {job.extraction?.dhl_job_number || job.job_id}
                        </CardTitle>
                        <div className="flex gap-2 items-center">
                          {job.csv_path && (
                            <Button 
                              variant="outline" 
                              size="sm"
                              onClick={() => {
                                const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
                                window.open(`${endpoint}/api/nz-audit/download-csv?csv_path=${encodeURIComponent(job.csv_path!)}`, '_blank');
                              }}
                            >
                              CSV
                            </Button>
                          )}
                          <Badge variant={job.success ? "default" : "destructive"}>
                            {job.success ? 'Success' : 'Failed'}
                          </Badge>
                        </div>
                      </div>
                      {job.extraction && (
                        <CardDescription>
                          {job.extraction.import_export} | Entry: {job.extraction.entry_number} | HAWB: {job.extraction.hawb}
                        </CardDescription>
                      )}
                      {job.job_folder && (
                        <div className="text-xs text-muted-foreground mt-1 font-mono truncate">
                          📁 {job.job_folder.split('/').slice(-2).join('/')}
                        </div>
                      )}
                    </CardHeader>
                    <CardContent>
                      {job.error && (
                        <p className="text-sm text-destructive mb-4">{job.error}</p>
                      )}
                      
                      {job.extraction && (
                        <div className="mb-4">
                          <h4 className="text-sm font-semibold mb-2">Extraction</h4>
                          <div className="grid grid-cols-4 gap-2 text-xs">
                            <div>
                              <span className="text-muted-foreground">Month:</span>{' '}
                              {job.extraction.audit_month}
                            </div>
                            <div>
                              <span className="text-muted-foreground">Broker:</span>{' '}
                              {job.extraction.broker}
                            </div>
                            <div>
                              <span className="text-muted-foreground">Entry Date:</span>{' '}
                              {job.extraction.entry_date}
                            </div>
                            <div>
                              <span className="text-muted-foreground">TL:</span>{' '}
                              {job.extraction.tl || '-'}
                            </div>
                          </div>
                        </div>
                      )}

                      {job.header_validation && (
                        <div>
                          <h4 className="text-sm font-semibold mb-2">Header Validations</h4>
                          <div className="grid grid-cols-2 gap-2 text-xs">
                            <div className="flex justify-between items-center py-1 border-b">
                              <span>Client code/name</span>
                              {getStatusBadge(job.header_validation.client_code_name_correct)}
                            </div>
                            <div className="flex justify-between items-center py-1 border-b">
                              <span>Supplier/Cnee</span>
                              {getStatusBadge(job.header_validation.supplier_or_cnee_correct)}
                            </div>
                            <div className="flex justify-between items-center py-1 border-b">
                              <span>Invoice Number</span>
                              {getStatusBadge(job.header_validation.invoice_number_correct)}
                            </div>
                            <div className="flex justify-between items-center py-1 border-b">
                              <span>VFD</span>
                              {getStatusBadge(job.header_validation.vfd_correct)}
                            </div>
                            <div className="flex justify-between items-center py-1 border-b">
                              <span>Currency</span>
                              {getStatusBadge(job.header_validation.currency_correct)}
                            </div>
                            <div className="flex justify-between items-center py-1 border-b">
                              <span>Incoterm</span>
                              {getStatusBadge(job.header_validation.incoterm_correct)}
                            </div>
                            <div className="flex justify-between items-center py-1 border-b">
                              <span>Freight Zero</span>
                              {getStatusBadge(job.header_validation.freight_zero_if_inclusive_incoterm)}
                            </div>
                            <div className="flex justify-between items-center py-1 border-b">
                              <span>Freight Correct</span>
                              {getStatusBadge(job.header_validation.freight_correct)}
                            </div>
                            <div className="flex justify-between items-center py-1 border-b">
                              <span>Load Port</span>
                              {getStatusBadge(job.header_validation.load_port_correct)}
                            </div>
                            <div className="flex justify-between items-center py-1 border-b">
                              <span>Relationship</span>
                              {getStatusBadge(job.header_validation.relationship_indicator_correct)}
                            </div>
                          </div>
                        </div>
                      )}

                      {job.auditor_comments && (
                        <div className="mt-4 p-2 bg-muted/50 rounded text-xs">
                          <span className="font-semibold">Comments:</span> {job.auditor_comments}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

