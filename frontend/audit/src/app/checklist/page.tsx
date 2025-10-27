'use client';

import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';

interface CheckItem {
    id: string;
    auditing_criteria: string;
    description: string;
    checking_logic: string;
    pass_conditions: string;
    compare_fields: {
        source_doc: string;
        source_field: string | string[];
        target_doc: string;
        target_field: string | string[];
    };
}

interface ChecklistData {
    version: string;
    region: string;
    description: string;
    last_updated: string;
    categories: {
        header: {
            name: string;
            description: string;
            checks: CheckItem[];
        };
        valuation: {
            name: string;
            description: string;
            checks: CheckItem[];
        };
    };
}

interface ChecklistResponse {
    success: boolean;
    region: string;
    content: ChecklistData;
    file_path: string;
}

export default function ChecklistPage() {
    const [region, setRegion] = useState<'AU' | 'NZ'>('AU');
    const [checklist, setChecklist] = useState<ChecklistData | null>(null);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);
    const [hasChanges, setHasChanges] = useState(false);
    const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

    // Load checklist when region changes
    useEffect(() => {
        loadChecklist();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [region]);

    const loadChecklist = async () => {
        setLoading(true);
        setError(null);
        setSuccess(null);

        try {
            const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            const response = await fetch(`${endpoint}/api/checklist/${region}`);

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to load checklist');
            }

            const data: ChecklistResponse = await response.json();
            setChecklist(data.content);
            setHasChanges(false);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load checklist');
            console.error('Load error:', err);
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        if (!checklist) return;

        setSaving(true);
        setError(null);
        setSuccess(null);

        try {
            const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            const response = await fetch(`${endpoint}/api/checklist/${region}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ content: checklist }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to save checklist');
            }

            const data = await response.json();
            setSuccess(`${data.message}`);
            setHasChanges(false);
        } catch (err) {
            setError(err instanceof Error ? `${err.message}` : 'Failed to save checklist');
            console.error('Save error:', err);
        } finally {
            setSaving(false);
        }
    };

    const handleReset = () => {
        loadChecklist();
    };

    const updateCheck = (category: 'header' | 'valuation', index: number, updates: Partial<CheckItem>) => {
        if (!checklist) return;

        const newChecklist = { ...checklist };
        newChecklist.categories[category].checks[index] = {
            ...newChecklist.categories[category].checks[index],
            ...updates,
        };
        setChecklist(newChecklist);
        setHasChanges(true);
        setError(null);
        setSuccess(null);
    };

    const updateCheckCompareField = (
        category: 'header' | 'valuation',
        index: number,
        field: keyof CheckItem['compare_fields'],
        value: string | string[]
    ) => {
        if (!checklist) return;

        const newChecklist = { ...checklist };
        newChecklist.categories[category].checks[index].compare_fields[field] = value as never;
        setChecklist(newChecklist);
        setHasChanges(true);
        setError(null);
        setSuccess(null);
    };

    const deleteCheck = (category: 'header' | 'valuation', index: number) => {
        if (!checklist) return;
        if (!confirm('Are you sure you want to delete this check?')) return;

        const newChecklist = { ...checklist };
        const checkId = newChecklist.categories[category].checks[index].id;
        newChecklist.categories[category].checks.splice(index, 1);
        
        // Remove from expanded rows if it was expanded
        const newExpandedRows = new Set(expandedRows);
        newExpandedRows.delete(checkId);
        setExpandedRows(newExpandedRows);
        
        setChecklist(newChecklist);
        setHasChanges(true);
        setError(null);
        setSuccess(null);
    };

    const addNewCheck = (category: 'header' | 'valuation') => {
        if (!checklist) return;

        const newChecklist = { ...checklist };
        const checks = newChecklist.categories[category].checks;
        const lastId = checks.length > 0 ? checks[checks.length - 1].id : `${region.toLowerCase()}_${category[0]}_000`;
        const idParts = lastId.split('_');
        const newNum = (parseInt(idParts[idParts.length - 1]) + 1).toString().padStart(3, '0');
        const newId = `${region.toLowerCase()}_${category[0]}_${newNum}`;

        const newCheck: CheckItem = {
            id: newId,
            auditing_criteria: 'New check',
            description: '',
            checking_logic: '',
            pass_conditions: '',
            compare_fields: {
                source_doc: 'entry_print',
                source_field: '',
                target_doc: 'commercial_invoice',
                target_field: '',
            },
        };

        newChecklist.categories[category].checks.push(newCheck);
        setChecklist(newChecklist);
        setHasChanges(true);
        setError(null);
        setSuccess(null);
    };

    const toggleRow = (checkId: string) => {
        const newExpandedRows = new Set(expandedRows);
        if (newExpandedRows.has(checkId)) {
            newExpandedRows.delete(checkId);
        } else {
            newExpandedRows.add(checkId);
        }
        setExpandedRows(newExpandedRows);
    };

    const expandAll = (category: 'header' | 'valuation') => {
        if (!checklist) return;
        const newExpandedRows = new Set(expandedRows);
        checklist.categories[category].checks.forEach((check) => {
            newExpandedRows.add(check.id);
        });
        setExpandedRows(newExpandedRows);
    };

    const collapseAll = (category: 'header' | 'valuation') => {
        if (!checklist) return;
        const newExpandedRows = new Set(expandedRows);
        checklist.categories[category].checks.forEach((check) => {
            newExpandedRows.delete(check.id);
        });
        setExpandedRows(newExpandedRows);
    };

    if (loading) {
        return (
            <div className="h-screen bg-background flex items-center justify-center">
                <p className="text-muted-foreground">Loading checklist...</p>
            </div>
        );
    }

    if (!checklist) {
        return (
            <div className="h-screen bg-background flex items-center justify-center">
                <p className="text-destructive">Failed to load checklist</p>
            </div>
        );
    }

    return (
        <div className="h-screen bg-background flex flex-col">
            {/* Fixed Header */}
            <div className="border-b bg-background/95 backdrop-blur supports-backdrop-filter:bg-background/60 sticky top-0 z-10">
                <div className="max-w-7xl mx-auto px-4 py-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <h1 className="text-2xl font-semibold tracking-tight">
                                Checklist Manager
                            </h1>
                            <p className="text-sm text-muted-foreground mt-1">
                                Edit checklist configurations
                            </p>
                        </div>
                        <div className="flex items-center gap-3">
                            <select
                                value={region}
                                onChange={(e) => setRegion(e.target.value as 'AU' | 'NZ')}
                                className="p-2 border rounded-md text-sm"
                                disabled={loading || saving}
                            >
                                <option value="AU">Australia (AU)</option>
                                <option value="NZ">New Zealand (NZ)</option>
                            </select>
                            
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={handleReset}
                                disabled={loading || saving || !hasChanges}
                            >
                                Reset
                            </Button>
                            <Button
                                variant="default"
                                size="sm"
                                onClick={handleSave}
                                disabled={loading || saving || !hasChanges}
                            >
                                {saving ? 'Saving...' : 'Save Changes'}
                            </Button>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => window.location.href = '/'}
                            >
                                ← Back
                            </Button>
                        </div>
                    </div>

                    {/* Status Messages */}
                    {(error || success || hasChanges) && (
                        <div className="mt-3 flex gap-2">
                            {hasChanges && !error && !success && (
                                <Badge variant="outline" className="text-amber-600 border-amber-600">
                                    ● Unsaved changes
                                </Badge>
                            )}
                            {error && (
                                <Badge variant="destructive">{error}</Badge>
                            )}
                            {success && (
                                <Badge className="bg-green-600">{success}</Badge>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* Scrollable Content */}
            <div className="flex-1 overflow-y-auto">
                <div className="max-w-7xl mx-auto p-4 space-y-4">
                    {/* Header Checks */}
                    <Card className="gap-0">
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle className="flex items-center gap-2">
                                        Header-Level Checks
                                        <Badge variant="secondary">
                                            {checklist.categories.header.checks.length}
                                        </Badge>
                                    </CardTitle>
                                </div>
                                <div className="flex gap-2">
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => expandAll('header')}
                                    >
                                        Expand All
                                    </Button>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => collapseAll('header')}
                                    >
                                        Collapse All
                                    </Button>
                                    <Button
                                        variant="default"
                                        size="sm"
                                        onClick={() => addNewCheck('header')}
                                    >
                                        + Add Check
                                    </Button>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent className="p-0 px-4">
                            <ChecksTable
                                checks={checklist.categories.header.checks}
                                category="header"
                                expandedRows={expandedRows}
                                onToggleRow={toggleRow}
                                onUpdate={updateCheck}
                                onUpdateCompareField={updateCheckCompareField}
                                onDelete={deleteCheck}
                            />
                        </CardContent>
                    </Card>

                    {/* Valuation Checks */}
                    <Card className="gap-0">
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle className="flex items-center gap-2">
                                        Valuation Checks
                                        <Badge variant="secondary">
                                            {checklist.categories.valuation.checks.length}
                                        </Badge>
                                    </CardTitle>
                                </div>
                                <div className="flex gap-2">
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => expandAll('valuation')}
                                    >
                                        Expand All
                                    </Button>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => collapseAll('valuation')}
                                    >
                                        Collapse All
                                    </Button>
                                    <Button
                                        variant="default"
                                        size="sm"
                                        onClick={() => addNewCheck('valuation')}
                                    >
                                        + Add Check
                                    </Button>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent className="p-0 px-4">
                            <ChecksTable
                                checks={checklist.categories.valuation.checks}
                                category="valuation"
                                expandedRows={expandedRows}
                                onToggleRow={toggleRow}
                                onUpdate={updateCheck}
                                onUpdateCompareField={updateCheckCompareField}
                                onDelete={deleteCheck}
                            />
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    );
}

interface ChecksTableProps {
    checks: CheckItem[];
    category: 'header' | 'valuation';
    expandedRows: Set<string>;
    onToggleRow: (checkId: string) => void;
    onUpdate: (category: 'header' | 'valuation', index: number, updates: Partial<CheckItem>) => void;
    onUpdateCompareField: (
        category: 'header' | 'valuation',
        index: number,
        field: keyof CheckItem['compare_fields'],
        value: string | string[]
    ) => void;
    onDelete: (category: 'header' | 'valuation', index: number) => void;
}

function ChecksTable({
    checks,
    category,
    expandedRows,
    onToggleRow,
    onUpdate,
    onUpdateCompareField,
    onDelete,
}: ChecksTableProps) {
    return (
        <div className="overflow-x-auto">
            <table className="w-full">
                <thead>
                    <tr className="border-b bg-muted/50">
                        <th className="text-left p-3 text-sm font-medium w-32">Check ID</th>
                        <th className="text-center p-3 text-sm font-medium w-20">#</th>
                        <th className="text-left p-3 text-sm font-medium">Auditing Criteria</th>
                        <th className="text-right p-3 text-sm font-medium w-48">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {checks.map((check, index) => (
                        <CheckTableRow
                            key={check.id}
                            check={check}
                            index={index}
                            category={category}
                            isExpanded={expandedRows.has(check.id)}
                            onToggle={() => onToggleRow(check.id)}
                            onUpdate={(updates) => onUpdate(category, index, updates)}
                            onUpdateCompareField={(field, value) => onUpdateCompareField(category, index, field, value)}
                            onDelete={() => onDelete(category, index)}
                        />
                    ))}
                </tbody>
            </table>
        </div>
    );
}

interface CheckTableRowProps {
    check: CheckItem;
    index: number;
    category: string;
    isExpanded: boolean;
    onToggle: () => void;
    onUpdate: (updates: Partial<CheckItem>) => void;
    onUpdateCompareField: (field: keyof CheckItem['compare_fields'], value: string | string[]) => void;
    onDelete: () => void;
}

function CheckTableRow({
    check,
    index,
    isExpanded,
    onToggle,
    onUpdate,
    onUpdateCompareField,
    onDelete,
}: CheckTableRowProps) {
    return (
        <>
            {/* Main Row */}
            <tr className="border-b hover:bg-muted/30 transition-colors">
                <td className="p-3">
                    <Badge variant="outline" className="font-mono text-xs">
                        {check.id}
                    </Badge>
                </td>
                <td className="p-3 text-center text-sm text-muted-foreground">
                    {index + 1}
                </td>
                <td className="p-3">
                    <Input
                        value={check.auditing_criteria}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                            onUpdate({ auditing_criteria: e.target.value })
                        }
                        className="font-medium"
                        placeholder="Auditing criteria"
                    />
                </td>
                <td className="p-3">
                    <div className="flex gap-2 justify-end">
                        <Button variant="outline" size="sm" onClick={onToggle}>
                            {isExpanded ? 'Collapse' : 'Expand'}
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={onDelete}
                            className="text-destructive hover:text-destructive"
                        >
                            Delete
                        </Button>
                    </div>
                </td>
            </tr>

            {/* Expanded Details Row */}
            {isExpanded && (
                <tr className="border-b bg-muted/10">
                    <td colSpan={4} className="p-4">
                        <div className="space-y-2 max-w-6xl">
                            {/* Description */}
                            <div className="space-y-2">
                                <label className="text-sm font-medium">Description</label>
                                <textarea
                                    value={check.description}
                                    onChange={(e) => onUpdate({ description: e.target.value })}
                                    className="w-full min-h-[60px] p-2 text-sm border rounded-md resize-y"
                                    placeholder="Detailed description of the check"
                                />
                            </div>

                            {/* Checking Logic */}
                            <div className="space-y-2">
                                <label className="text-sm font-medium">Checking Logic</label>
                                <textarea
                                    value={check.checking_logic}
                                    onChange={(e) => onUpdate({ checking_logic: e.target.value })}
                                    className="w-full min-h-[60px] p-2 text-sm border rounded-md resize-y"
                                    placeholder="How to perform this check"
                                />
                            </div>

                            {/* Pass Conditions */}
                            <div className="space-y-2">
                                <label className="text-sm font-medium">Pass Conditions</label>
                                <textarea
                                    value={check.pass_conditions}
                                    onChange={(e) => onUpdate({ pass_conditions: e.target.value })}
                                    className="w-full min-h-[60px] p-2 text-sm border rounded-md resize-y"
                                    placeholder="When this check should pass"
                                />
                            </div>

                            {/* Compare Fields */}
                            <div className="space-y-3 pt-2 border-t">
                                <label className="text-sm font-medium">Compare Fields</label>
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <label className="text-xs text-muted-foreground">Source Document</label>
                                        <select
                                            value={check.compare_fields.source_doc}
                                            onChange={(e) => onUpdateCompareField('source_doc', e.target.value)}
                                            className="w-full p-2 text-sm border rounded-md"
                                        >
                                            <option value="entry_print">Entry Print</option>
                                            <option value="commercial_invoice">Commercial Invoice</option>
                                            <option value="air_waybill">Air Waybill</option>
                                        </select>
                                    </div>
                                    <div className="space-y-2">
                                        <label className="text-xs text-muted-foreground">Target Document</label>
                                        <select
                                            value={check.compare_fields.target_doc}
                                            onChange={(e) => onUpdateCompareField('target_doc', e.target.value)}
                                            className="w-full p-2 text-sm border rounded-md"
                                        >
                                            <option value="entry_print">Entry Print</option>
                                            <option value="commercial_invoice">Commercial Invoice</option>
                                            <option value="air_waybill">Air Waybill</option>
                                        </select>
                                    </div>
                                    <div className="space-y-2">
                                        <label className="text-xs text-muted-foreground">
                                            Source Field(s){' '}
                                            <span className="text-muted-foreground/50">(comma-separated)</span>
                                        </label>
                                        <Input
                                            value={
                                                Array.isArray(check.compare_fields.source_field)
                                                    ? check.compare_fields.source_field.join(', ')
                                                    : check.compare_fields.source_field
                                            }
                                            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                                                const value = e.target.value;
                                                const hasComma = value.includes(',');
                                                onUpdateCompareField(
                                                    'source_field',
                                                    hasComma ? value.split(',').map((s: string) => s.trim()) : value
                                                );
                                            }}
                                            className="text-sm font-mono"
                                            placeholder="field_name or field1, field2"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <label className="text-xs text-muted-foreground">
                                            Target Field(s){' '}
                                            <span className="text-muted-foreground/50">(comma-separated)</span>
                                        </label>
                                        <Input
                                            value={
                                                Array.isArray(check.compare_fields.target_field)
                                                    ? check.compare_fields.target_field.join(', ')
                                                    : check.compare_fields.target_field
                                            }
                                            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                                                const value = e.target.value;
                                                const hasComma = value.includes(',');
                                                onUpdateCompareField(
                                                    'target_field',
                                                    hasComma ? value.split(',').map((s: string) => s.trim()) : value
                                                );
                                            }}
                                            className="text-sm font-mono"
                                            placeholder="field_name or field1, field2"
                                        />
                                    </div>
                                </div>
                            </div>
                        </div>
                    </td>
                </tr>
            )}
        </>
    );
}
