/**
 * Monaco Code Editor — reusable VS Code editor component.
 *
 * Features:
 * - Python syntax highlighting with spine-specific autocomplete
 * - Dark/light theme support with spine palette
 * - Minimap, word-wrap, line numbers
 * - Read-only mode for source code viewing
 * - Copy-to-clipboard button
 * - Configurable height / language
 */

import { useCallback, useState, useRef } from 'react';
import Editor, { type OnMount, type Monaco } from '@monaco-editor/react';
import type { editor } from 'monaco-editor';
import { Copy, Check, Maximize2, Minimize2, Sun, Moon } from 'lucide-react';

// ── Spine custom dark theme ─────────────────────────────────────────
function defineSpineThemes(monaco: Monaco) {
  monaco.editor.defineTheme('spine-dark', {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: 'comment', foreground: '6A737D', fontStyle: 'italic' },
      { token: 'keyword', foreground: '79B8FF' },
      { token: 'string', foreground: '9ECBFF' },
      { token: 'number', foreground: 'F2CC60' },
      { token: 'type', foreground: 'B392F0' },
      { token: 'function', foreground: 'E1E4E8' },
      { token: 'variable', foreground: 'FFAB70' },
      { token: 'decorator', foreground: 'F97583' },
    ],
    colors: {
      'editor.background': '#0D1117',
      'editor.foreground': '#E1E4E8',
      'editor.lineHighlightBackground': '#161B22',
      'editor.selectionBackground': '#1F6FEB44',
      'editorCursor.foreground': '#58A6FF',
      'editorLineNumber.foreground': '#484F58',
      'editorLineNumber.activeForeground': '#E1E4E8',
      'editor.inactiveSelectionBackground': '#1F6FEB22',
      'editorIndentGuide.background': '#21262D',
      'editorIndentGuide.activeBackground': '#30363D',
    },
  });

  monaco.editor.defineTheme('spine-light', {
    base: 'vs',
    inherit: true,
    rules: [
      { token: 'comment', foreground: '6A737D', fontStyle: 'italic' },
      { token: 'keyword', foreground: '0550AE' },
      { token: 'string', foreground: '0A3069' },
      { token: 'number', foreground: '0550AE' },
      { token: 'type', foreground: '8250DF' },
      { token: 'function', foreground: '24292F' },
      { token: 'decorator', foreground: 'CF222E' },
    ],
    colors: {
      'editor.background': '#FFFFFF',
      'editor.foreground': '#24292F',
      'editor.lineHighlightBackground': '#F6F8FA',
      'editor.selectionBackground': '#0969DA33',
      'editorCursor.foreground': '#0969DA',
      'editorLineNumber.foreground': '#8C959F',
      'editorLineNumber.activeForeground': '#24292F',
    },
  });
}

// ── Spine Python completions ────────────────────────────────────────
function registerSpineCompletions(monaco: Monaco) {
  monaco.languages.registerCompletionItemProvider('python', {
    provideCompletionItems: () => ({
      suggestions: [
        // Core classes
        {
          label: 'Workflow',
          kind: monaco.languages.CompletionItemKind.Class,
          insertText: 'Workflow(\n    name="${1:my_workflow}",\n    steps=[${2}],\n    domain="${3:default}",\n)',
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          detail: 'spine.Workflow',
          documentation: 'Create a new Workflow with named steps and execution policy.',
        },
        {
          label: 'Step',
          kind: monaco.languages.CompletionItemKind.Class,
          insertText: 'Step(\n    name="${1:step_name}",\n    handler=${2:handler_fn},\n    depends_on=[${3}],\n)',
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          detail: 'spine.Step',
          documentation: 'Define a workflow step with handler function and dependencies.',
        },
        {
          label: 'Pipeline',
          kind: monaco.languages.CompletionItemKind.Class,
          insertText: 'Pipeline(\n    name="${1:pipeline_name}",\n    steps=[\n        ${2}\n    ],\n)',
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          detail: 'spine.Pipeline',
          documentation: 'Create a pipeline with sequential processing steps.',
        },
        // Decorators
        {
          label: '@task',
          kind: monaco.languages.CompletionItemKind.Snippet,
          insertText: '@task(name="${1:task_name}", retries=${2:3})\ndef ${3:my_task}(ctx):\n    ${4:pass}',
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          detail: 'Task decorator',
          documentation: 'Decorate a function as a spine task with retry policy.',
        },
        {
          label: '@pipeline_step',
          kind: monaco.languages.CompletionItemKind.Snippet,
          insertText: '@pipeline_step(order=${1:1})\ndef ${2:process}(ctx, data):\n    ${3:return data}',
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          detail: 'Pipeline step decorator',
        },
        // Context patterns
        {
          label: 'ctx.params',
          kind: monaco.languages.CompletionItemKind.Property,
          insertText: 'ctx.params["${1:key}"]',
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          detail: 'Access run parameters',
        },
        {
          label: 'ctx.outputs',
          kind: monaco.languages.CompletionItemKind.Property,
          insertText: 'ctx.outputs["${1:step_name}"]',
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          detail: 'Access outputs from previous steps',
        },
        {
          label: 'ctx.set_output',
          kind: monaco.languages.CompletionItemKind.Method,
          insertText: 'ctx.set_output("${1:key}", ${2:value})',
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          detail: 'Set step output value',
        },
        // Common imports
        {
          label: 'import spine',
          kind: monaco.languages.CompletionItemKind.Snippet,
          insertText: 'from spine.core import Workflow, Step, Pipeline\nfrom spine.execution import run_workflow',
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          detail: 'Standard spine imports',
        },
      ],
    }),
  });
}

// ── Component Props ─────────────────────────────────────────────────
export interface CodeEditorProps {
  /** Source code value */
  value: string;
  /** Programming language (default: python) */
  language?: string;
  /** Editor height (CSS value) */
  height?: string;
  /** Read-only mode — for source viewers */
  readOnly?: boolean;
  /** Called on content change (only when not readOnly) */
  onChange?: (value: string) => void;
  /** Show minimap (default: true for large files) */
  minimap?: boolean;
  /** Show line numbers (default: true) */
  lineNumbers?: boolean;
  /** Initial theme — 'dark' or 'light' */
  theme?: 'dark' | 'light';
  /** Show toolbar with copy/theme/fullscreen buttons */
  showToolbar?: boolean;
  /** Optional file name to show in toolbar */
  fileName?: string;
  /** Optional line to highlight / scroll to */
  highlightLine?: number;
  /** Word wrap mode */
  wordWrap?: 'on' | 'off' | 'wordWrapColumn';
  /** Additional CSS class for the wrapper */
  className?: string;
}

export default function CodeEditor({
  value,
  language = 'python',
  height = '400px',
  readOnly = false,
  onChange,
  minimap = true,
  lineNumbers = true,
  theme: initialTheme = 'dark',
  showToolbar = true,
  fileName,
  highlightLine,
  wordWrap = 'on',
  className = '',
}: CodeEditorProps) {
  const [copied, setCopied] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [currentTheme, setCurrentTheme] = useState(initialTheme);
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);

  const themeName = currentTheme === 'dark' ? 'spine-dark' : 'spine-light';

  const handleMount: OnMount = useCallback(
    (editorInstance, monaco) => {
      editorRef.current = editorInstance;

      // Register custom themes
      defineSpineThemes(monaco);
      monaco.editor.setTheme(themeName);

      // Register spine Python completions
      registerSpineCompletions(monaco);

      // Highlight specific line if requested
      if (highlightLine) {
        editorInstance.revealLineInCenter(highlightLine);
        editorInstance.deltaDecorations([], [
          {
            range: new monaco.Range(highlightLine, 1, highlightLine, 1),
            options: {
              isWholeLine: true,
              className: currentTheme === 'dark'
                ? 'bg-yellow-900/30'
                : 'bg-yellow-100',
              glyphMarginClassName: 'bg-yellow-400',
            },
          },
        ]);
      }

      // Add keyboard shortcut for copy
      editorInstance.addAction({
        id: 'spine-copy-all',
        label: 'Copy All Code',
        keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyC],
        run: () => {
          navigator.clipboard.writeText(editorInstance.getValue());
        },
      });
    },
    [themeName, highlightLine, currentTheme],
  );

  const handleCopy = () => {
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const toggleTheme = () => {
    const next = currentTheme === 'dark' ? 'light' : 'dark';
    setCurrentTheme(next);
    if (editorRef.current) {
      // Theme will be applied via the Editor component's theme prop change
    }
  };

  const toggleExpand = () => setIsExpanded(!isExpanded);

  const lineCount = value.split('\n').length;
  const showMinimap = minimap && lineCount > 40;

  const wrapperClass = isExpanded
    ? 'fixed inset-4 z-50 flex flex-col rounded-xl overflow-hidden shadow-2xl'
    : `rounded-xl overflow-hidden ${className}`;

  return (
    <div className={wrapperClass}>
      {/* Backdrop for expanded mode */}
      {isExpanded && (
        <div
          className="fixed inset-0 bg-black/50 -z-10"
          onClick={toggleExpand}
        />
      )}

      {/* Toolbar */}
      {showToolbar && (
        <div
          className={`flex items-center justify-between px-3 py-1.5 ${
            currentTheme === 'dark'
              ? 'bg-[#161B22] border-b border-gray-800'
              : 'bg-gray-50 border-b border-gray-200'
          }`}
        >
          <div className="flex items-center gap-2">
            {/* Traffic light dots */}
            <div className="flex gap-1.5">
              <div className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
              <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/80" />
              <div className="w-2.5 h-2.5 rounded-full bg-green-500/80" />
            </div>
            {fileName && (
              <span className={`text-xs font-mono ml-2 ${
                currentTheme === 'dark' ? 'text-gray-400' : 'text-gray-500'
              }`}>
                {fileName}
              </span>
            )}
            {readOnly && (
              <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded font-medium ${
                currentTheme === 'dark'
                  ? 'bg-gray-800 text-gray-500'
                  : 'bg-gray-200 text-gray-500'
              }`}>
                read-only
              </span>
            )}
          </div>

          <div className="flex items-center gap-1">
            {/* Language badge */}
            <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded font-medium ${
              currentTheme === 'dark'
                ? 'bg-spine-900/40 text-spine-400'
                : 'bg-spine-50 text-spine-600'
            }`}>
              {language}
            </span>

            {/* Line count */}
            <span className={`text-[10px] px-1.5 py-0.5 ${
              currentTheme === 'dark' ? 'text-gray-500' : 'text-gray-400'
            }`}>
              {lineCount} lines
            </span>

            {/* Theme toggle */}
            <button
              onClick={toggleTheme}
              className={`p-1 rounded transition-colors ${
                currentTheme === 'dark'
                  ? 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'
                  : 'text-gray-400 hover:text-gray-600 hover:bg-gray-200'
              }`}
              title={`Switch to ${currentTheme === 'dark' ? 'light' : 'dark'} theme`}
            >
              {currentTheme === 'dark' ? <Sun className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
            </button>

            {/* Copy */}
            <button
              onClick={handleCopy}
              className={`p-1 rounded transition-colors ${
                currentTheme === 'dark'
                  ? 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'
                  : 'text-gray-400 hover:text-gray-600 hover:bg-gray-200'
              }`}
              title="Copy code"
            >
              {copied ? (
                <Check className="w-3.5 h-3.5 text-green-400" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
            </button>

            {/* Expand / Minimize */}
            <button
              onClick={toggleExpand}
              className={`p-1 rounded transition-colors ${
                currentTheme === 'dark'
                  ? 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'
                  : 'text-gray-400 hover:text-gray-600 hover:bg-gray-200'
              }`}
              title={isExpanded ? 'Minimize' : 'Expand'}
            >
              {isExpanded ? (
                <Minimize2 className="w-3.5 h-3.5" />
              ) : (
                <Maximize2 className="w-3.5 h-3.5" />
              )}
            </button>
          </div>
        </div>
      )}

      {/* Editor */}
      <Editor
        height={isExpanded ? '100%' : height}
        language={language}
        value={value}
        theme={themeName}
        onChange={(val) => onChange?.(val ?? '')}
        onMount={handleMount}
        loading={
          <div className={`flex items-center justify-center h-full ${
            currentTheme === 'dark' ? 'bg-[#0D1117]' : 'bg-white'
          }`}>
            <div className="flex items-center gap-2 text-gray-400 text-sm">
              <div className="w-4 h-4 border-2 border-spine-400 border-t-transparent rounded-full animate-spin" />
              Loading editor…
            </div>
          </div>
        }
        options={{
          readOnly,
          minimap: { enabled: showMinimap },
          fontSize: 13,
          fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Menlo, Monaco, 'Courier New', monospace",
          fontLigatures: true,
          lineNumbers: lineNumbers ? 'on' : 'off',
          scrollBeyondLastLine: false,
          wordWrap,
          automaticLayout: true,
          tabSize: 4,
          renderWhitespace: 'selection',
          bracketPairColorization: { enabled: true },
          guides: {
            bracketPairs: true,
            indentation: true,
          },
          padding: { top: 12, bottom: 12 },
          smoothScrolling: true,
          cursorBlinking: 'smooth',
          cursorSmoothCaretAnimation: 'on',
          renderLineHighlight: readOnly ? 'none' : 'all',
          scrollbar: {
            verticalScrollbarSize: 8,
            horizontalScrollbarSize: 8,
            useShadows: false,
          },
          overviewRulerBorder: false,
          hideCursorInOverviewRuler: true,
          contextmenu: !readOnly,
          copyWithSyntaxHighlighting: true,
          // Disable suggestions in readOnly mode
          quickSuggestions: readOnly ? false : { other: true, strings: true, comments: false },
          suggestOnTriggerCharacters: !readOnly,
          parameterHints: { enabled: !readOnly },
        }}
      />
    </div>
  );
}
