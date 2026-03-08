'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

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

interface AuditProgress {
  completed: number;
  failed: number;
  total: number;
  skipped: number;
  pending: number;
  percent: number;
  is_running: boolean;
  updated_at: string;
}

interface AuditStatusResponse {
  success: boolean;
  folder_name: string;
  is_running: boolean;
  task_error: string | null;
  run_id: string | null;
  total_jobs: number;
  completed_jobs: number;
  pending_jobs: number;
  progress: AuditProgress | null;
  csv_path: string | null;
  xlsx_path: string | null;
}

const API_ENDPOINT = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function AUAuditPage() {
  const router = useRouter();
  const [folders, setFolders] = useState<GroupedFolder[]>([]);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [auditStatus, setAuditStatus] = useState<AuditStatusResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [jobList, setJobList] = useState<JobListResponse | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    loadGroupedFolders();
  }, []);

  useEffect(() => {
    const fetchJobs = async () => {
      if (!selectedFolder) {
        setJobList(null);
        return;
      }
      try {
        const response = await fetch(`${API_ENDPOINT}/api/au-audit/jobs?folder_name=${encodeURIComponent(selectedFolder)}`);
        if (!response.ok) throw new Error('Failed to load job list');
        const data: JobListResponse = await response.json();
        setJobList(data);
      } catch (err) {
        setErrorMsg(err instanceof Error ? err.message : 'Failed to load job list');
      }
    };
    fetchJobs();
  }, [selectedFolder]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const loadGroupedFolders = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const response = await fetch(`${API_ENDPOINT}/api/au-audit/grouped-folders`);
      if (!response.ok) throw new Error('Failed to load grouped folders');
      const data: ListGroupedFoldersResponse = await response.json();
      setFolders(data.folders);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to load folders');
    } finally {
      setLoading(false);
    }
  };

  const pollStatus = useCallback(async (folderName: string) => {
    try {
      const response = await fetch(`${API_ENDPOINT}/api/au-audit/status?folder_name=${encodeURIComponent(folderName)}`);
      if (!response.ok) return;
      const data: AuditStatusResponse = await response.json();
      setAuditStatus(data);

      // Refresh job list while polling
      const jobsResponse = await fetch(`${API_ENDPOINT}/api/au-audit/jobs?folder_name=${encodeURIComponent(folderName)}`);
      if (jobsResponse.ok) {
        const jobsData: JobListResponse = await jobsResponse.json();
        setJobList(jobsData);
      }

      // Stop polling when done
      if (!data.is_running) {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
        setProcessing(false);
        await loadGroupedFolders();
      }
    } catch {
      // Ignore poll errors (server might be restarting)
    }
  }, []);

  const startPolling = useCallback((folderName: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    // Poll immediately, then every 3 seconds
    pollStatus(folderName);
    pollRef.current = setInterval(() => pollStatus(folderName), 3000);
  }, [pollStatus]);

  const handleRunAudit = async (resumeFailedOnly: boolean = true) => {
    if (!selectedFolder) return;
    setProcessing(true);
    setErrorMsg(null);
    setAuditStatus(null);
    try {
      const params = new URLSearchParams({
        folder_name: selectedFolder,
        resume_failed_only: resumeFailedOnly.toString()
      });
      const response = await fetch(`${API_ENDPOINT}/api/au-audit/process?${params}`, { method: 'POST' });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Audit failed');
      }
      // Start polling for progress
      startPolling(selectedFolder);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Audit failed');
      setProcessing(false);
    }
  };

  const handleDownloadCSV = () => {
    if (!auditStatus?.csv_path) return;
    window.open(`${API_ENDPOINT}/api/au-audit/download-csv?csv_path=${encodeURIComponent(auditStatus.csv_path)}`, '_blank');
  };

  const handleDownloadXLSX = () => {
    if (!auditStatus?.xlsx_path) return;
    window.open(`${API_ENDPOINT}/api/au-audit/download-xlsx?xlsx_path=${encodeURIComponent(auditStatus.xlsx_path)}`, '_blank');
  };

  const progress = auditStatus?.progress;
  const isRunning = processing || (auditStatus?.is_running ?? false);
  const isDone = auditStatus && !auditStatus.is_running && (auditStatus.completed_jobs > 0 || auditStatus.task_error);

  return (
    <div className="h-screen bg-background flex flex-col p-4 relative">
      <div className="max-w-7xl mx-auto w-full flex flex-col h-full">
        <header className="mb-4 flex items-center justify-between shrink-0">
          <h1 className="text-3xl font-semibold tracking-tight">AU Audit</h1>
          <nav className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => router.push('/')}>Back</Button>
            <Button variant="outline" size="sm" onClick={() => router.push('/output')}>Output</Button>
          </nav>
        </header>

        <div className="grid grid-cols-3 gap-6 flex-1 overflow-hidden">
          <div className="col-span-1 space-y-4 pr-2">
            <Card>
              <CardHeader><CardTitle>Grouped Folders</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <Button onClick={loadGroupedFolders} variant="outline" size="sm" className="w-full" disabled={loading}>
                  {loading ? 'Loading...' : 'Refresh'}
                </Button>
                <div className="space-y-2 max-h-[300px] overflow-y-auto">
                  {folders.map(f => (
                    <div key={f.name} onClick={() => setSelectedFolder(f.name)} className={`p-3 rounded-md cursor-pointer ${selectedFolder === f.name ? 'bg-primary text-primary-foreground' : 'bg-muted/50 hover:bg-muted'}`}>
                      <div className="flex justify-between items-center mb-1">
                        <span className="font-medium text-sm truncate">{f.name}</span>
                        <Badge variant={selectedFolder === f.name ? "secondary" : "outline"}>{f.job_count} jobs</Badge>
                      </div>
                      <div className="flex justify-between text-xs opacity-70">
                        <span>{new Date(f.created).toLocaleDateString()}</span>
                        {f.completed_jobs > 0 && <span className="text-green-500">{f.completed_jobs}/{f.job_count}</span>}
                      </div>
                    </div>
                  ))}
                </div>
                {selectedFolder && (
                  <div className="space-y-2">
                    <Button onClick={() => handleRunAudit(true)} disabled={isRunning} className="w-full">
                      {isRunning ? 'Running...' : (folders.find(f => f.name === selectedFolder)?.completed_jobs ?? 0) > 0 ? 'Resume Audit' : 'Run AU Audit'}
                    </Button>
                    {(folders.find(f => f.name === selectedFolder)?.completed_jobs ?? 0) > 0 && (
                      <Button onClick={() => handleRunAudit(false)} variant="outline" className="w-full border-orange-500 text-orange-600" disabled={isRunning}>
                        Restart All Jobs
                      </Button>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {selectedFolder && jobList && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Jobs</CardTitle>
                  <CardDescription>{jobList.completed} done, {jobList.pending} pending</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 max-h-[calc(100vh-580px)] overflow-y-auto">
                    {jobList.jobs.map(j => (
                      <div key={j.job_id} className={`p-2 rounded-md border text-sm ${j.status === 'completed' ? 'bg-green-50 border-green-200' : 'bg-muted/50'}`}>
                        <div className="flex justify-between items-center">
                          <span className="font-medium truncate">{j.hawb || j.job_id}</span>
                          <Badge variant={j.status === 'completed' ? 'default' : 'secondary'}>{j.status === 'completed' ? 'Done' : 'Pending'}</Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {errorMsg && (
              <Card className="border-red-500">
                <CardContent className="pt-4 pb-4">
                  <p className="text-sm text-red-500">{errorMsg}</p>
                </CardContent>
              </Card>
            )}
          </div>

          <div className="col-span-2 space-y-4 overflow-y-auto pr-2 pb-4">
            {/* Progress / Running State */}
            {isRunning && auditStatus && (
              <Card>
                <CardHeader>
                  <div className="flex justify-between items-center">
                    <CardTitle>Audit In Progress</CardTitle>
                    <span className="text-2xl font-bold tabular-nums">
                      {auditStatus.completed_jobs} / {auditStatus.total_jobs}
                    </span>
                  </div>
                  <CardDescription>
                    {auditStatus.total_jobs > 0
                      ? `${Math.round((auditStatus.completed_jobs / auditStatus.total_jobs) * 100)}% complete`
                      : 'Starting...'}
                    {progress?.failed ? ` \u00b7 ${progress.failed} failed` : ''}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {/* Progress bar */}
                    <div className="w-full bg-muted rounded-full h-4 overflow-hidden flex">
                      <div
                        className="bg-primary h-full transition-all duration-500"
                        style={{ width: `${auditStatus.total_jobs > 0 ? (auditStatus.completed_jobs / auditStatus.total_jobs) * 100 : 0}%` }}
                      />
                      {(progress?.failed ?? 0) > 0 && (
                        <div
                          className="bg-red-500 h-full transition-all duration-500"
                          style={{ width: `${auditStatus.total_jobs > 0 ? ((progress?.failed ?? 0) / auditStatus.total_jobs) * 100 : 0}%` }}
                        />
                      )}
                    </div>
                    <div className="grid grid-cols-3 gap-4 text-center">
                      <div>
                        <div className="text-2xl font-bold text-green-600 tabular-nums">{auditStatus.completed_jobs}</div>
                        <div className="text-xs text-muted-foreground">Completed</div>
                      </div>
                      <div>
                        <div className="text-2xl font-bold text-red-500 tabular-nums">{progress?.failed ?? 0}</div>
                        <div className="text-xs text-muted-foreground">Failed</div>
                      </div>
                      <div>
                        <div className="text-2xl font-bold tabular-nums">{auditStatus.pending_jobs}</div>
                        <div className="text-xs text-muted-foreground">Remaining</div>
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground text-center">
                      You can close this page or stop the server. Resume by clicking &quot;Resume Audit&quot; again.
                    </p>
                  </div>
                </CardContent>
              </Card>
            )}
            {isRunning && !auditStatus && (
              <Card>
                <CardContent className="pt-6 pb-6 text-center">
                  <div className="flex flex-col items-center gap-3">
                    <div className="h-10 w-10 rounded-full border-4 border-primary border-t-transparent animate-spin" />
                    <p className="text-sm text-muted-foreground">Starting audit...</p>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Completed State */}
            {isDone && !isRunning && (
              <Card>
                <CardHeader>
                  <div className="flex justify-between items-center">
                    <div>
                      <CardTitle>
                        {auditStatus.task_error ? 'Audit Failed' : 'Audit Complete'}
                      </CardTitle>
                      {auditStatus.run_id && (
                        <CardDescription className="mt-1">Run: {auditStatus.run_id}</CardDescription>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-2xl font-bold tabular-nums">
                        {auditStatus.completed_jobs} / {auditStatus.total_jobs}
                      </span>
                      <div className="flex gap-2">
                        {auditStatus.csv_path && <Button onClick={handleDownloadCSV} size="sm" variant="outline">CSV</Button>}
                        {auditStatus.xlsx_path && <Button onClick={handleDownloadXLSX} size="sm">XLSX</Button>}
                      </div>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  {auditStatus.task_error ? (
                    <p className="text-sm text-red-500">{auditStatus.task_error}</p>
                  ) : (
                    <>
                      <div className="w-full bg-muted rounded-full h-3 overflow-hidden flex mb-4">
                        <div
                          className="bg-green-500 h-full"
                          style={{ width: `${auditStatus.total_jobs > 0 ? (auditStatus.completed_jobs / auditStatus.total_jobs) * 100 : 0}%` }}
                        />
                        {(progress?.failed ?? 0) > 0 && (
                          <div
                            className="bg-red-500 h-full"
                            style={{ width: `${auditStatus.total_jobs > 0 ? ((progress?.failed ?? 0) / auditStatus.total_jobs) * 100 : 0}%` }}
                          />
                        )}
                      </div>
                      <div className="grid grid-cols-3 gap-8 text-center">
                        <div>
                          <div className="text-3xl font-bold text-green-600 tabular-nums">{auditStatus.completed_jobs}</div>
                          <div className="text-xs text-muted-foreground">Completed</div>
                        </div>
                        <div>
                          <div className="text-3xl font-bold text-red-500 tabular-nums">{progress?.failed ?? 0}</div>
                          <div className="text-xs text-muted-foreground">Failed</div>
                        </div>
                        <div>
                          <div className="text-3xl font-bold tabular-nums">{auditStatus.total_jobs}</div>
                          <div className="text-xs text-muted-foreground">Total</div>
                        </div>
                      </div>
                    </>
                  )}
                  {auditStatus.pending_jobs > 0 && !auditStatus.task_error && (
                    <p className="text-sm text-orange-600 mt-4 text-center">
                      {auditStatus.pending_jobs} jobs remaining. Click &quot;Resume Audit&quot; to continue.
                    </p>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Idle State */}
            {!isRunning && !isDone && (
              <Card>
                <CardContent className="pt-6 pb-32 text-center text-muted-foreground">
                  Select a folder and click &quot;Run AU Audit&quot; to start
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
