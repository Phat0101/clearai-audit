'use client';

import { useState, useCallback, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

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
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [region, setRegion] = useState<'AU' | 'NZ'>('AU');

  // Prevent page refresh/close during processing
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (processing) {
        e.preventDefault();
        e.returnValue = '';
        return '';
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [processing]);

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
      console.log('Processing successful:', data);
      
      // Small delay to ensure success message is logged, then redirect
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // Redirect to output page after successful processing
      router.push('/output');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Processing failed');
      console.error('Processing error:', err);
      setProcessing(false);
    }
  };

  const clearAll = () => {
    setFiles([]);
    setResult(null);
    setError(null);
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
                  <h3 className="text-lg font-semibold mb-2">Processing Documents</h3>
                  <p className="text-sm text-muted-foreground mb-4">
                    Please wait while we analyze your files...
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
            <h1 className="text-3xl font-semibold tracking-tight">
              Clear.ai Audit
            </h1>
            <nav className="flex gap-2">
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => router.push('/output')}
              >
                Browse Output
              </Button>
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => router.push('/checklist')}
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
            {!result && (
              <Card>
                <CardContent className="pt-6 pb-32 text-center">
                  <p className="text-sm text-muted-foreground">
                    Upload and process files to see grouping results here
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
                    <Card key={index} className="gap-0">
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
          </div>
        </div>
      </div>
    </div>
  );
}
