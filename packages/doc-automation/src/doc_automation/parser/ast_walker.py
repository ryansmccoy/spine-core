"""
AST Walker for Python source code.

Walks the Abstract Syntax Tree of Python files to extract class and method
information, including docstrings for documentation extraction.

Example:
    >>> walker = ASTWalker()
    >>> classes = walker.walk_file(Path("src/my_module.py"))
    >>> for cls in classes:
    ...     print(f"{cls.name}: {len(cls.methods)} methods")
"""

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


@dataclass
class MethodInfo:
    """Information about a class method.
    
    Attributes:
        name: Method name
        signature: Full method signature
        docstring: Method docstring (if present)
        line_number: Line number where method is defined
        is_public: Whether method is public (doesn't start with _)
        decorators: List of decorator names
        parameters: List of parameter names
        return_annotation: Return type annotation (if present)
    """
    name: str
    signature: str
    docstring: str | None
    line_number: int
    is_public: bool
    decorators: list[str] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    return_annotation: str | None = None


@dataclass
class ClassInfo:
    """Information about a Python class.
    
    Attributes:
        name: Class name
        module: Module path (e.g., 'entityspine.resolver')
        file_path: Path to source file
        line_number: Line number where class is defined
        docstring: Class docstring (if present)
        methods: List of methods in the class
        bases: List of base class names
        decorators: List of decorator names
        is_dataclass: Whether class is a dataclass
    """
    name: str
    module: str
    file_path: Path
    line_number: int
    docstring: str | None
    methods: list[MethodInfo] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    is_dataclass: bool = False
    
    @property
    def has_extended_docstring(self) -> bool:
        """Check if class has extended documentation annotations."""
        if not self.docstring:
            return False
        
        # Check for any of the extended section markers
        markers = [
            "Manifesto:", "Architecture:", "Features:", "Guardrails:",
            "Examples:", "Context:", "Tags:", "Doc-Types:", "ADR:",
            "Changelog:", "Performance:", "Feature-Guide:", 
            "Unified-Data-Model:", "Architecture-Doc:"
        ]
        return any(marker in self.docstring for marker in markers)
    
    @property
    def public_methods(self) -> list[MethodInfo]:
        """Get only public methods."""
        return [m for m in self.methods if m.is_public]


class ASTWalker:
    """Walk Python AST and extract class/method information.
    
    Manifesto:
        Code is the source of truth. Documentation should be extracted
        FROM code, not written separately and hope it stays in sync.
        The AST Walker is the foundation - it reads code structure
        so we can mine documentation from docstrings.
    
    Architecture:
        ```
        Python File (.py)
              │
              ▼
        ast.parse() ──► AST Tree
              │
              ▼
        ast.walk() ──► Visit Nodes
              │
              ├──► ClassDef nodes ──► ClassInfo
              │         │
              │         └──► FunctionDef ──► MethodInfo
              │
              └──► Results: List[ClassInfo]
        ```
    
    Features:
        - Extract all classes from Python file
        - Get method signatures and docstrings
        - Track line numbers for source links
        - Detect dataclasses and decorators
        - Filter public vs private methods
    
    Examples:
        >>> walker = ASTWalker()
        >>> classes = walker.walk_file(Path("src/resolver.py"))
        >>> classes[0].name
        'EntityResolver'
    
    Guardrails:
        - Do NOT parse non-Python files
          ✅ Check file extension first
        - Do NOT assume all files are valid Python
          ✅ Handle SyntaxError gracefully
    
    Tags:
        - parser
        - ast
        - code_analysis
        - core_infrastructure
    
    Doc-Types:
        - API_REFERENCE (section: "Parser Module", priority: 8)
        - ARCHITECTURE (section: "Code Analysis", priority: 6)
    """
    
    def walk_file(self, file_path: Path) -> list[ClassInfo]:
        """Extract all classes from a Python file.
        
        Args:
            file_path: Path to Python source file
            
        Returns:
            List of ClassInfo objects for each class found
            
        Raises:
            FileNotFoundError: If file doesn't exist
            SyntaxError: If file is not valid Python
            
        Example:
            >>> walker = ASTWalker()
            >>> classes = walker.walk_file(Path("example.py"))
            >>> len(classes)
            3
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if file_path.suffix != ".py":
            raise ValueError(f"Not a Python file: {file_path}")
        
        with open(file_path, encoding="utf-8") as f:
            source = f.read()
        
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            # Re-raise with more context
            raise SyntaxError(f"Failed to parse {file_path}: {e}") from e
        
        # Derive module name from file path
        module = self._derive_module_name(file_path)
        
        classes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_info = self._extract_class(node, file_path, module)
                classes.append(class_info)
        
        return classes
    
    def walk_directory(self, dir_path: Path, skip_patterns: list[str] | None = None) -> Iterator[ClassInfo]:
        """Walk a directory and extract classes from all Python files.
        
        Args:
            dir_path: Directory to walk
            skip_patterns: Patterns to skip (e.g., ["test_", "__pycache__"])
            
        Yields:
            ClassInfo for each class found
            
        Example:
            >>> walker = ASTWalker()
            >>> for cls in walker.walk_directory(Path("src")):
            ...     print(cls.name)
        """
        skip_patterns = skip_patterns or ["test_", "__pycache__", ".pyc"]
        
        for py_file in dir_path.rglob("*.py"):
            # Check skip patterns
            path_str = str(py_file)
            if any(pattern in path_str for pattern in skip_patterns):
                continue
            
            try:
                for class_info in self.walk_file(py_file):
                    yield class_info
            except (SyntaxError, UnicodeDecodeError) as e:
                # Log but continue with other files
                print(f"Warning: Skipping {py_file}: {e}")
                continue
    
    def _extract_class(self, node: ast.ClassDef, file_path: Path, module: str) -> ClassInfo:
        """Extract ClassInfo from an AST ClassDef node.
        
        Args:
            node: AST ClassDef node
            file_path: Source file path
            module: Module name
            
        Returns:
            ClassInfo object
        """
        # Get docstring
        docstring = ast.get_docstring(node)
        
        # Get methods
        methods = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_info = self._extract_method(item)
                methods.append(method_info)
        
        # Get base classes
        bases = [self._get_name(base) for base in node.bases]
        
        # Get decorators
        decorators = [self._get_name(d) for d in node.decorator_list]
        is_dataclass = "dataclass" in decorators
        
        return ClassInfo(
            name=node.name,
            module=module,
            file_path=file_path,
            line_number=node.lineno,
            docstring=docstring,
            methods=methods,
            bases=bases,
            decorators=decorators,
            is_dataclass=is_dataclass,
        )
    
    def _extract_method(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> MethodInfo:
        """Extract MethodInfo from an AST FunctionDef node.
        
        Args:
            node: AST FunctionDef or AsyncFunctionDef node
            
        Returns:
            MethodInfo object
        """
        # Get docstring
        docstring = ast.get_docstring(node)
        
        # Build signature
        signature = self._build_signature(node)
        
        # Get parameters
        parameters = [arg.arg for arg in node.args.args]
        
        # Get return annotation
        return_annotation = None
        if node.returns:
            return_annotation = self._get_annotation(node.returns)
        
        # Get decorators
        decorators = [self._get_name(d) for d in node.decorator_list]
        
        return MethodInfo(
            name=node.name,
            signature=signature,
            docstring=docstring,
            line_number=node.lineno,
            is_public=not node.name.startswith("_"),
            decorators=decorators,
            parameters=parameters,
            return_annotation=return_annotation,
        )
    
    def _build_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """Build a method signature string.
        
        Args:
            node: AST FunctionDef node
            
        Returns:
            Signature string like "method(self, arg1: str, arg2: int = 0) -> bool"
        """
        parts = []
        
        # Handle arguments
        args = node.args
        
        # Regular args
        num_defaults = len(args.defaults)
        num_args = len(args.args)
        
        for i, arg in enumerate(args.args):
            arg_str = arg.arg
            
            # Add type annotation
            if arg.annotation:
                arg_str += f": {self._get_annotation(arg.annotation)}"
            
            # Add default value
            default_idx = i - (num_args - num_defaults)
            if default_idx >= 0:
                default = args.defaults[default_idx]
                arg_str += f" = {self._get_literal(default)}"
            
            parts.append(arg_str)
        
        # *args
        if args.vararg:
            vararg_str = f"*{args.vararg.arg}"
            if args.vararg.annotation:
                vararg_str += f": {self._get_annotation(args.vararg.annotation)}"
            parts.append(vararg_str)
        
        # **kwargs
        if args.kwarg:
            kwarg_str = f"**{args.kwarg.arg}"
            if args.kwarg.annotation:
                kwarg_str += f": {self._get_annotation(args.kwarg.annotation)}"
            parts.append(kwarg_str)
        
        sig = f"{node.name}({', '.join(parts)})"
        
        # Add return type
        if node.returns:
            sig += f" -> {self._get_annotation(node.returns)}"
        
        return sig
    
    def _get_name(self, node: ast.expr) -> str:
        """Get the name from an AST expression node.
        
        Args:
            node: AST expression node
            
        Returns:
            Name as string
        """
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return self._get_name(node.func)
        elif isinstance(node, ast.Subscript):
            return f"{self._get_name(node.value)}[{self._get_annotation(node.slice)}]"
        else:
            return ast.unparse(node) if hasattr(ast, 'unparse') else str(node)
    
    def _get_annotation(self, node: ast.expr) -> str:
        """Get type annotation as string.
        
        Args:
            node: AST expression node
            
        Returns:
            Annotation as string
        """
        if hasattr(ast, 'unparse'):
            return ast.unparse(node)
        return self._get_name(node)
    
    def _get_literal(self, node: ast.expr) -> str:
        """Get literal value as string.
        
        Args:
            node: AST expression node
            
        Returns:
            Literal as string
        """
        if isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Name):
            return node.id
        elif hasattr(ast, 'unparse'):
            return ast.unparse(node)
        return "..."
    
    def _derive_module_name(self, file_path: Path) -> str:
        """Derive module name from file path.
        
        Args:
            file_path: Path to Python file
            
        Returns:
            Module name like 'package.subpackage.module'
        """
        # Remove .py extension
        parts = list(file_path.with_suffix("").parts)
        
        # Try to find src directory and use path after it
        try:
            src_idx = parts.index("src")
            parts = parts[src_idx + 1:]
        except ValueError:
            # No src directory, use filename only
            parts = [parts[-1]]
        
        return ".".join(parts)
