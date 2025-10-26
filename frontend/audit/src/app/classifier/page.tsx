'use client';

import { useState, useEffect, useRef } from 'react';

interface UploadedItem {
  id: string;
  description: string;
  supplier_name?: string;
  supplier?: string;
  'supplier name'?: string;
}

interface ClassificationResult {
  id: string;
  description: string;
  supplier_name?: string;
  best_suggested_hs_code: string;
  best_suggested_stat_code?: string;
  best_suggested_stat_key?: string;
  best_suggested_tco_link?: string;
  other_suggested_codes?: Array<{
    hs_code: string;
    stat_code?: string;
    stat_key?: string;
    tco_link?: string;
  }>;
  total_time_seconds?: number;
  reasoning?: string;
}

const PROGRESS_STEPS = [
  { threshold: 0, text: 'Understanding the products' },
  { threshold: 20, text: 'Researching the products' },
  { threshold: 45, text: 'Classifying the products' },
  { threshold: 70, text: 'Synthesising the recommendations' },
  { threshold: 90, text: 'Finalising the responses' },
];

export default function Classifier() {
  const [uploadedData, setUploadedData] = useState<UploadedItem[]>([]);
  const [classificationResults, setClassificationResults] = useState<ClassificationResult[]>([]);
  const [currentRegion, setCurrentRegion] = useState<'au' | 'nz'>('au');
  const [token, setToken] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [status, setStatus] = useState<{ message: string; type: 'loading' | 'error' | 'success' } | null>(null);
  const [isClassifying, setIsClassifying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [showProgress, setShowProgress] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load token from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem('apiToken');
      if (saved) setToken(saved);
    } catch (e) {
      console.error('Failed to load token from localStorage', e);
    }
  }, []);

  // Save token to localStorage
  useEffect(() => {
    try {
      if (token) localStorage.setItem('apiToken', token.trim());
    } catch (e) {
      console.error('Failed to save token to localStorage', e);
    }
  }, [token]);

  const getProgressStep = (percent: number) => {
    for (let i = PROGRESS_STEPS.length - 1; i >= 0; i--) {
      if (percent >= PROGRESS_STEPS[i].threshold) return i;
    }
    return 0;
  };

  const parseCSV = (csv: string): UploadedItem[] => {
    const lines = csv.trim().split('\n');
    const headers = lines[0].split(',').map(h => h.trim().toLowerCase());

    return lines
      .slice(1)
      .map((line, index) => {
        const values = line.split(',').map(v => v.trim().replace(/^["']|["']$/g, ''));
        const item: Record<string, string> = {};
        headers.forEach((header, i) => {
          item[header] = values[i] || '';
        });

        if (!item.id) {
          item.id = String(index + 1);
        }

        return item as unknown as UploadedItem;
      })
      .filter(item => item.description && item.description.trim());
  };

  const handleFile = (file: File) => {
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setStatus({ message: 'Please select a CSV file.', type: 'error' });
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const csv = e.target?.result as string;
        const data = parseCSV(csv);

        if (data.length === 0) {
          setStatus({ message: 'CSV file appears to be empty.', type: 'error' });
          return;
        }

        const firstRow = data[0];
        if (!firstRow.id || !firstRow.description) {
          setStatus({ message: 'CSV must have "id" and "description" columns.', type: 'error' });
          return;
        }

        setUploadedData(data);
        setStatus({ message: `Successfully loaded ${data.length} items from CSV`, type: 'success' });
        setClassificationResults([]);
      } catch (error) {
        setStatus({ message: 'Error parsing CSV file: ' + (error instanceof Error ? error.message : 'Unknown error'), type: 'error' });
      }
    };
    reader.readAsText(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFile(files[0]);
    }
  };

  const classifyItems = async () => {
    if (uploadedData.length === 0) {
      setStatus({ message: 'Please upload a CSV file first.', type: 'error' });
      return;
    }

    const trimmedToken = token.trim();
    if (!trimmedToken) {
      setStatus({ message: 'Missing API token. Paste the token first.', type: 'error' });
      return;
    }

    setIsClassifying(true);
    setStatus({ message: 'Classifying items... This may take a while.', type: 'loading' });
    setShowProgress(true);
    setProgress(0);

    try {
      const requestBody = {
        items: uploadedData.map(item => ({
          id: item.id,
          description: item.description,
          supplier_name: item.supplier_name || item.supplier || item['supplier name'] || undefined,
        })),
      };

      // Simulate progress
      const totalDurationSec = 70 + Math.floor(Math.random() * 51);
      const startTs = Date.now();
      const progressInterval = setInterval(() => {
        const elapsed = (Date.now() - startTs) / 1000;
        const planned = Math.min(95, (elapsed / totalDurationSec) * 100);
        setProgress(planned);
      }, 1000);

      const endpoint = `/api/classify/${currentRegion}`;
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer ' + trimmedToken,
        },
        body: JSON.stringify(requestBody),
      });

      clearInterval(progressInterval);
      setProgress(100);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: response.statusText }));
        throw new Error(`HTTP ${response.status}: ${errorData.error || response.statusText}`);
      }

      const data = await response.json();
      setClassificationResults(data.results);
      setStatus({ message: `Successfully classified ${data.results.length} items!`, type: 'success' });

      setTimeout(() => {
        setShowProgress(false);
      }, 1000);
    } catch (error) {
      setStatus({ message: 'Error during classification: ' + (error instanceof Error ? error.message : 'Unknown error'), type: 'error' });
      setShowProgress(false);
    } finally {
      setIsClassifying(false);
    }
  };

  const downloadResults = () => {
    if (classificationResults.length === 0) return;

    const headers =
      currentRegion === 'nz'
        ? ['id', 'description', 'supplier_name', 'best_suggested_hs_code', 'best_suggested_stat_key', 'other_codes', 'total_time_seconds', 'reasoning']
        : ['id', 'description', 'supplier_name', 'best_suggested_hs_code', 'best_suggested_stat_code', 'best_suggested_tco_link', 'other_codes', 'total_time_seconds', 'reasoning'];

    const idToSupplier = new Map(uploadedData.map(item => [String(item.id), item.supplier_name || item.supplier || item['supplier name'] || '']));

    const csvContent = [
      headers.join(','),
      ...classificationResults.map(result => {
        const supplier = result.supplier_name || idToSupplier.get(String(result.id)) || '';
        if (currentRegion === 'nz') {
          const other = (result.other_suggested_codes || []).map(c => `${c.hs_code}/${c.stat_key}`).join('; ');
          return [
            result.id,
            `"${result.description.replace(/"/g, '""')}"`,
            `"${supplier.replace(/"/g, '""')}"`,
            result.best_suggested_hs_code,
            result.best_suggested_stat_key || '',
            `"${other}"`,
            result.total_time_seconds || '',
            `"${(result.reasoning || '').replace(/"/g, '""')}"`,
          ].join(',');
        } else {
          const other = (result.other_suggested_codes || []).map(c => `${c.hs_code}/${c.stat_code}`).join('; ');
          return [
            result.id,
            `"${result.description.replace(/"/g, '""')}"`,
            `"${supplier.replace(/"/g, '""')}"`,
            result.best_suggested_hs_code,
            result.best_suggested_stat_code || '',
            result.best_suggested_tco_link || '',
            `"${other}"`,
            result.total_time_seconds || '',
            `"${(result.reasoning || '').replace(/"/g, '""')}"`,
          ].join(',');
        }
      }),
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `tariff_classification_results_${currentRegion}_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  };

  const totalItems = classificationResults.length > 0 ? classificationResults.length : uploadedData.length;
  const avgTime =
    classificationResults.length > 0
      ? (classificationResults.reduce((sum, r) => sum + (r.total_time_seconds || 0), 0) / classificationResults.length).toFixed(1)
      : '-';
  const tcoCount = classificationResults.length > 0 ? classificationResults.filter(r => r.best_suggested_tco_link).length : '-';

  const idToSupplier = new Map(uploadedData.map(item => [String(item.id), item.supplier_name || item.supplier || item['supplier name'] || '']));

  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <div className="max-w-7xl mx-auto bg-white rounded-lg shadow-lg overflow-hidden">
        {/* Header */}
        <div className="bg-gray-800 text-white px-6 py-6 text-center border-b-4 border-gray-700">
          <h1 className="text-3xl font-semibold mb-2">Clear AI Tariff Classifier</h1>
          <p className="text-sm opacity-90">Upload CSV files to classify items with Australian tariff codes</p>
        </div>

        {/* Upload Section */}
        <div className="px-6 py-6 border-b border-gray-200">
          <div
            className={`border-2 border-dashed rounded-md p-6 mb-4 transition-all cursor-pointer text-center ${
              isDragOver ? 'border-gray-700 bg-gray-100' : 'border-gray-300 bg-gray-50 hover:border-gray-500 hover:bg-gray-100'
            }`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <div className="text-base font-medium text-gray-700 mb-2">Drop your CSV file here or click to browse</div>
            <div className="text-sm text-gray-500">CSV format: id, description[, supplier_name] (supplier_name optional)</div>
          </div>
          <input ref={fileInputRef} type="file" accept=".csv" className="hidden" onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])} />

          <div className="flex flex-wrap gap-4 items-center mb-4">
            <label htmlFor="tokenInput" className="font-medium text-sm">
              API Token
            </label>
            <input
              id="tokenInput"
              type={showToken ? 'text' : 'password'}
              placeholder="Paste Bearer token"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              className="flex-1 min-w-[260px] px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="button"
              onClick={() => setShowToken(!showToken)}
              className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 transition-colors font-medium text-sm"
            >
              {showToken ? 'Hide' : 'Show'}
            </button>

            <label htmlFor="regionSelect" className="font-medium text-sm">
              Region
            </label>
            <select
              id="regionSelect"
              value={currentRegion}
              onChange={(e) => setCurrentRegion(e.target.value as 'au' | 'nz')}
              className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="au">Australia (AU)</option>
              <option value="nz">New Zealand (NZ)</option>
            </select>
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="px-5 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 transition-colors font-medium text-sm"
            >
              Choose File
            </button>
            <button
              onClick={classifyItems}
              disabled={uploadedData.length === 0 || isClassifying}
              className="px-5 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors font-medium text-sm disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              Classify Items
            </button>
          </div>

          {/* Status */}
          {status && (
            <div
              className={`mt-4 px-4 py-3 rounded-md font-medium text-sm ${
                status.type === 'loading'
                  ? 'bg-cyan-50 text-cyan-800 border border-cyan-200'
                  : status.type === 'error'
                  ? 'bg-red-50 text-red-800 border border-red-200'
                  : 'bg-green-50 text-green-800 border border-green-200'
              }`}
            >
              {status.message}
            </div>
          )}

          {/* Progress Bar */}
          {showProgress && (
            <>
              <div className="mt-3 w-full h-1.5 bg-gray-200 rounded-full overflow-hidden">
                <div className="h-full bg-blue-600 transition-all duration-300" style={{ width: `${progress}%` }}></div>
              </div>
              <div className="mt-2 text-gray-600 text-sm">
                {PROGRESS_STEPS.map((step, idx) => (
                  <span key={idx}>
                    {idx === getProgressStep(progress) ? <strong>{step.text}</strong> : step.text}
                    {idx < PROGRESS_STEPS.length - 1 && ' → '}
                  </span>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Results Section */}
        {(uploadedData.length > 0 || classificationResults.length > 0) && (
          <div className="px-6 py-6">
            {/* Summary */}
            <div className="bg-gray-50 px-5 py-5 rounded-md mb-6 grid grid-cols-1 sm:grid-cols-3 gap-5 border border-gray-200">
              <div className="text-center">
                <span className="block text-2xl font-bold text-gray-700">{totalItems}</span>
                <span className="text-xs text-gray-600 uppercase tracking-wider">Total Items</span>
              </div>
              <div className="text-center">
                <span className="block text-2xl font-bold text-gray-700">
                  {isClassifying ? <span className="inline-block w-5 h-5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin"></span> : avgTime === '-' ? '-' : `${avgTime}s`}
                </span>
                <span className="text-xs text-gray-600 uppercase tracking-wider">Avg Time</span>
              </div>
              <div className="text-center">
                <span className="block text-2xl font-bold text-gray-700">
                  {isClassifying ? <span className="inline-block w-5 h-5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin"></span> : tcoCount}
                </span>
                <span className="text-xs text-gray-600 uppercase tracking-wider">TCO Available</span>
              </div>
            </div>

            {/* Results Table */}
            <div className="bg-white border border-gray-200 rounded-md overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-600 text-white text-left">
                    <th className="px-2 py-2.5 font-semibold text-xs uppercase tracking-wide">ID</th>
                    <th className="px-2 py-2.5 font-semibold text-xs uppercase tracking-wide">Description</th>
                    <th className="px-2 py-2.5 font-semibold text-xs uppercase tracking-wide">Supplier</th>
                    <th className="px-2 py-2.5 font-semibold text-xs uppercase tracking-wide">Best HS Code</th>
                    <th className="px-2 py-2.5 font-semibold text-xs uppercase tracking-wide">{currentRegion === 'nz' ? 'Best Stat Key' : 'Best Stat Code'}</th>
                    <th className="px-2 py-2.5 font-semibold text-xs uppercase tracking-wide">TCO Link</th>
                    <th className="px-2 py-2.5 font-semibold text-xs uppercase tracking-wide">Other Codes</th>
                    <th className="px-2 py-2.5 font-semibold text-xs uppercase tracking-wide">Time (s)</th>
                    <th className="px-2 py-2.5 font-semibold text-xs uppercase tracking-wide">Reasoning</th>
                  </tr>
                </thead>
                <tbody>
                  {classificationResults.length > 0
                    ? classificationResults.map((result) => {
                        const supplier = result.supplier_name || idToSupplier.get(String(result.id)) || '';
                        const bestStat = currentRegion === 'nz' ? result.best_suggested_stat_key || '-' : result.best_suggested_stat_code || '-';
                        return (
                          <tr key={result.id} className="border-b border-gray-200 hover:bg-gray-50">
                            <td className="px-2 py-2.5 font-semibold text-gray-700">{result.id}</td>
                            <td className="px-2 py-2.5 max-w-xs truncate text-gray-900" title={result.description}>
                              {result.description}
                            </td>
                            <td className="px-2 py-2.5">
                              {supplier ? (
                                <span className="inline-block bg-blue-50 text-blue-800 border border-blue-200 px-2 py-0.5 rounded-full text-xs max-w-[220px] truncate">
                                  {supplier}
                                </span>
                              ) : (
                                <span className="text-gray-900">-</span>
                              )}
                            </td>
                            <td className="px-2 py-2.5">
                              <code className="bg-gray-100 text-gray-900 px-1.5 py-0.5 rounded text-xs font-mono font-medium">{result.best_suggested_hs_code}</code>
                            </td>
                            <td className="px-2 py-2.5">
                              <code className="bg-gray-100 text-gray-900 px-1.5 py-0.5 rounded text-xs font-mono font-medium">{bestStat}</code>
                            </td>
                            <td className="px-2 py-2.5 text-gray-900">
                              {currentRegion === 'nz' ? (
                                '-'
                              ) : result.best_suggested_tco_link ? (
                                <a href={result.best_suggested_tco_link} target="_blank" rel="noopener noreferrer" className="text-blue-600 text-xs font-medium hover:underline">
                                  TCO
                                </a>
                              ) : (
                                '-'
                              )}
                            </td>
                            <td className="px-2 py-2.5 max-w-[200px]">
                              {(result.other_suggested_codes || []).map((code, idx) => {
                                const stat = currentRegion === 'nz' ? code.stat_key : code.stat_code;
                                return (
                                  <div key={idx} className="mb-1 text-xs text-gray-900">
                                    <code className="bg-gray-100 text-gray-900 px-1 py-0.5 rounded font-mono">{code.hs_code}</code>
                                    <span className="text-gray-900">/</span>
                                    <code className="bg-gray-100 text-gray-900 px-1 py-0.5 rounded font-mono">{stat}</code>
                                    {currentRegion !== 'nz' && code.tco_link && (
                                      <>
                                        {' '}
                                        <a href={code.tco_link} target="_blank" rel="noopener noreferrer" className="text-blue-600 font-medium hover:underline">
                                          TCO
                                        </a>
                                      </>
                                    )}
                                  </div>
                                );
                              })}
                            </td>
                            <td className="px-2 py-2.5">
                              <span className="inline-block bg-gray-100 text-gray-700 px-1.5 py-0.5 rounded text-xs font-medium min-w-[50px] text-center">
                                {(result.total_time_seconds || 0).toFixed(1)}s
                              </span>
                            </td>
                            <td className="px-2 py-2.5 max-w-md text-xs text-gray-700 leading-tight">{result.reasoning || '-'}</td>
                          </tr>
                        );
                      })
                    : uploadedData.map((item) => {
                        const supplier = item.supplier_name || item.supplier || item['supplier name'] || '';
                        return (
                          <tr key={item.id} className="border-b border-gray-200 hover:bg-gray-50">
                            <td className="px-2 py-2.5 font-semibold text-gray-700">{item.id}</td>
                            <td className="px-2 py-2.5 max-w-xs truncate text-gray-900" title={item.description}>
                              {item.description}
                            </td>
                            <td className="px-2 py-2.5">
                              {supplier ? (
                                <span className="inline-block bg-blue-50 text-blue-800 border border-blue-200 px-2 py-0.5 rounded-full text-xs max-w-[220px] truncate">
                                  {supplier}
                                </span>
                              ) : (
                                <span className="text-gray-900">-</span>
                              )}
                            </td>
                            <td className="px-2 py-2.5 text-gray-900">{isClassifying ? <span className="inline-block w-3.5 h-3.5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin"></span> : '-'}</td>
                            <td className="px-2 py-2.5 text-gray-900">{isClassifying ? <span className="inline-block w-3.5 h-3.5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin"></span> : '-'}</td>
                            <td className="px-2 py-2.5 text-gray-900">{isClassifying ? <span className="inline-block w-3.5 h-3.5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin"></span> : '-'}</td>
                            <td className="px-2 py-2.5 text-gray-900">{isClassifying ? <span className="inline-block w-3.5 h-3.5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin"></span> : '-'}</td>
                            <td className="px-2 py-2.5 text-gray-900">{isClassifying ? <span className="inline-block w-3.5 h-3.5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin"></span> : '-'}</td>
                            <td className="px-2 py-2.5 text-gray-900">{isClassifying ? <span className="inline-block w-3.5 h-3.5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin"></span> : '-'}</td>
                          </tr>
                        );
                      })}
                </tbody>
              </table>
            </div>

            {classificationResults.length > 0 && (
              <button onClick={downloadResults} className="mt-4 px-5 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors font-medium text-sm">
                Download Results CSV
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
