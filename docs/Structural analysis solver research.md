# Open-source solvers for a custom frame analysis engine

**PyNite is the strongest all-around choice for a custom 2D portal frame builder with a 3D upgrade path**, offering MIT licensing, a clean Python API, active maintenance by a practicing structural engineer, and native 3D beam elements ready when needed. But the most important insight from this research is that for a lightweight, interactive frame builder, **writing your own solver is not only viable — it may be optimal**. A 2D direct stiffness method implementation requires only 300–500 lines of focused code, gives you total control over the architecture, and avoids dependency and licensing headaches entirely. The open-source ecosystem then serves best as a reference library and validation benchmark rather than an embedded dependency.

This report evaluates 15+ open-source packages across two tiers — heavyweight FEM frameworks and lightweight frame-specific tools — and recommends strategies for three distinct paths: embedding an existing solver, scaling toward advanced 3D FEM, and building from scratch.

## The lightweight tools are what actually matter here

For a custom frame builder, the general-purpose FEM packages (CalculiX, Code_Aster, Elmer, MFEM, FreeFEM) are largely irrelevant. Most lack beam/frame elements entirely, require file-based I/O that kills interactivity, or carry heavyweight dependency chains unsuitable for embedding. The real candidates live in a different tier: purpose-built structural frame libraries designed as embeddable APIs.

**PyNite** stands out as the most complete option. Written in pure Python with NumPy/SciPy, it offers full **3D beam/frame elements with 6 DOF per node**, P-Δ geometric nonlinearity, modal analysis, load cases and combinations, tension/compression-only members, plate elements, and even shear wall modeling. Its MIT license permits unrestricted commercial use. With **671 GitHub stars**, 2,083 commits, and active maintenance by D. Craig Brinck (PE, SE), it is the most production-ready Python frame library available. The API is clean and imperative: create an `FEModel3D`, add nodes, members, loads, supports, then call `.analyze()`. Member forces are accessible via methods like `member.moment('Mz')`.

**anastruct** offers the cleanest 2D-specific API of any tool reviewed. A portal frame analysis requires roughly 10 lines of code. Compiled binary wheels (Cython/C extensions) deliver sub-millisecond solve times. Originally created by Ritchie Vink — who later built the Polars dataframe library — it has **438 stars** and active organizational maintenance. Its major limitation is that it is **2D-only with no 3D upgrade path**, and its **GPL v3 license** means derivative works must also be GPL, which is problematic for proprietary applications.

**Frame3DD** is the fastest raw solver (pure ANSI C, sub-microsecond for small frames) with both 2D and 3D support plus dynamic/modal analysis, but it has been effectively dormant since 2013 and operates as a standalone command-line program with file-based I/O — not an embeddable library. **pyCBA** is excellent but limited to 1D continuous beams — useful as a component within a larger tool but not a frame solver.

| Tool | Language | 2D/3D | Nonlinear | License | Stars | API quality | Interactive speed | Active |
|------|----------|-------|-----------|---------|-------|-------------|-------------------|--------|
| **PyNite** | Python | 3D | P-Δ, modal | **MIT** | 671 | Good | ~ms | Yes |
| **anastruct** | Python+C | 2D only | Geometric | GPL v3 | 438 | Excellent | <1 ms | Yes |
| **Frame3DD** | C | 2D+3D | Geometric | GPL v3 | — | None (CLI) | μs | No |
| **pyCBA** | Python | 1D beams | No | MIT | 75 | Excellent | <1 ms | Yes |
| **OpenSeesPy** | C++/Python | 3D | Full | Restrictive | 735 | Complex | ~10 ms | Yes |
| **OOFEM** | C++ | 2D+3D | Yes | LGPL-2.1 | 178 | C++ API | ~ms | Yes |

## Two emerging projects point toward the future architecture

**Stabileo** is a brand-new project (26 stars, 633 commits) that implements exactly the architecture pattern a modern web-based frame builder should follow: a **Rust solver compiled to WebAssembly** with a Svelte 5 frontend and Three.js 3D visualization. The solver runs on every edit — move a node, change a load, get instant results. It demonstrates that real-time structural analysis in the browser is not just feasible but already being built. The project is too immature to depend on, but it validates the approach.

**Awatif** is another critical reference — an open-source TypeScript structural analysis web app with **130 stars** and 1,348 commits. Its FEM solver is written entirely in TypeScript, supporting bar and beam elements with shell and solid elements planned. Created by a structural-engineer-turned-developer, it is the closest existing analog to a custom portal frame builder. Both projects prove that browser-native structural analysis with sub-second solve times is achievable with modern web technologies.

**OpenBeam** deserves mention as a proven C++ → WebAssembly compilation path. It uses Eigen3 for linear algebra, implements the direct stiffness method, and runs natively in the browser via Emscripten. A published Springer paper (2023) documents it as "the first application capable of running on the web and mobile devices that allows arbitrarily complex structures to be defined and calculated." Its scope is limited (2D, linear, static), but the architecture pattern is directly replicable.

## The heavyweight packages: when and why they matter

Among the major FEM frameworks, **only OpenSees and OOFEM are genuinely relevant** for structural frame analysis embedding. The others fail on fundamental criteria.

**OpenSees** is the gold standard for nonlinear structural analysis. Its Python API (`pip install openseespy`) makes it the only major FEM package that can be embedded as a standard Python library call with zero file I/O. It has purpose-built beam-column elements with fiber sections, P-delta and corotational geometric transformations, and hundreds of material models. The 2D-to-3D migration is trivial — change `ndm=2` to `ndm=3`. Frame-sized problems solve in milliseconds. With **735 stars**, v3.8.0 released February 2025, and an ecosystem of third-party tools (STKO, Build-X, NextFEM), it has the largest structural engineering community of any open-source solver. The critical caveat: **its UC Berkeley license prohibits commercial redistribution** without a paid license. For internal tools, research, or education, it is free. For a commercial product, contact UC Berkeley early.

**OOFEM** is the only general FEM package that has both dedicated beam2d/beam3d Timoshenko elements *and* a programmatic C++ API for embedding (via `DynamicDataReader`). Its **LGPL-2.1 license** permits commercial embedding without copyleft infection. With 178 stars and a focused structural engineering community (602 registered forum users), it is smaller but purposeful. The trade-off is less polished documentation and a smaller ecosystem for troubleshooting.

**CalculiX** (Fortran, standalone batch solver, file-based I/O, GPL) and **Code_Aster** (enormous dependency chain, French documentation, GPL) are designed for industrial-scale continuum mechanics — not interactive frame analysis. **MFEM** has the best API design and a BSD-3 license but has **zero beam or frame elements** — it is a continuum PDE solver only. **Elmer FEM** has limited beam elements but is a standalone solver suite not designed for embedding. **FreeFEM** uses its own domain-specific language with no external API and no structural elements.

| Package | Beam elements | Embeddable | License | Suitable for frames |
|---------|--------------|------------|---------|-------------------|
| **OpenSees** | Excellent | Yes (pip) | Commercial license needed | **Yes** |
| **OOFEM** | beam2d, beam3d | Yes (C++ API) | LGPL-2.1 | **Yes** |
| CalculiX | B31, B32 | No (file I/O) | GPL v2+ | Marginal |
| Code_Aster | Yes (400+ types) | No (heavy deps) | GPL | No |
| Elmer FEM | Limited | No (standalone) | GPL/LGPL mix | No |
| MFEM | **None** | Yes (excellent) | BSD-3 | **No** |
| FreeFEM | **None** | No (own DSL) | LGPL-3.0 | **No** |

## Building your own solver is more practical than it sounds

A 2D portal frame solver using the direct stiffness method requires: assembling 6×6 element stiffness matrices, transforming to global coordinates, assembling the global stiffness matrix via connectivity arrays, applying boundary conditions, solving the linear system, and back-calculating member forces. **This is 300–500 lines of focused code** in any language. The progression from 2D truss (2 DOF/node, 4×4 element matrices) to 2D frame (3 DOF/node, 6×6 matrices) to 3D frame (6 DOF/node, 12×12 matrices) is well-documented and incremental.

The best educational resources for this path include the **EngineeringSkills.com course series** by Dr. Seán Carroll, which walks through exactly this progression: 2D truss → 2D beam/frame → 3D space frame, all in Python. The anastruct and StructPy codebases are excellent references for understanding the implementation. PyNite's source code is particularly readable — organized by element type with derivation documents included.

**Performance is not a barrier at any language level.** For a typical portal frame (10–200 DOF), even pure Python loops solve in under a millisecond. Python with NumPy/SciPy handles **14,742 DOF** (a 3D concrete building with 7,065 beams) in under one second using banded solvers. For browser-based apps, JavaScript with typed arrays handles sub-1000 DOF frames in milliseconds. The key insight from benchmarks is that **solver choice and configuration matter far more than language** — using the wrong SciPy sparse solver settings can produce a 36× slowdown on identical hardware. The `pyPardiso` package (Intel MKL PARDISO) is a drop-in replacement that dramatically accelerates large sparse solves.

Real-world examples validate the build-your-own approach. The VIKTOR platform has deployed both anastruct and OpenSeesPy as backends for web-based structural analysis apps. CalcTree offers zero-setup OpenSeesPy environments. The Awatif project built a complete TypeScript FEM solver for browser use. And the StressIt educational project documented that replacing a pure JavaScript matrix solver with C compiled to WASM via Emscripten produced "orders of magnitude" faster calculations.

## Three recommended paths based on your priorities

**Path 1 — Lightweight, interactive frame engine (fast, embeddable, simple API):**
Use **PyNite** as your starting point if building a Python-backed application, or **write a custom TypeScript/Rust solver** if building a web app. PyNite gives you immediate 3D capability, MIT licensing, and a clean API. For web deployment, a custom solver compiled to WASM (following the Stabileo/OpenBeam pattern) delivers real-time interactivity. A 2D DSM solver is small enough (~300 lines) that writing your own eliminates dependency risk entirely. Start with 2D (3 DOF/node), validate against anastruct or textbook results, then extend to 3D (6 DOF/node) when ready.

**Path 2 — Scalability toward advanced FEM and 3D analysis:**
Use **OpenSees** (via OpenSeesPy) if licensing permits, or **OOFEM** if you need LGPL freedom. OpenSees offers the cleanest 2D→3D migration (`ndm=2` → `ndm=3`), the richest beam-column element library, and proven scalability to complex nonlinear analysis. OOFEM provides similar structural elements with a permissive LGPL-2.1 license and a C++ API suitable for tight integration, but has a smaller community. If you anticipate needing nonlinear material models, fiber sections, seismic analysis, or soil-structure interaction, OpenSees is unmatched. Budget for the commercial license early if you plan to distribute the application.

**Path 3 — Learn from the codebase and build your own solver:**
Study **anastruct** for the cleanest 2D implementation, **PyNite** for 3D element formulations, and **Frame3DD** for C-level numerical methods. The EngineeringSkills.com direct stiffness method course provides the theoretical scaffolding. StructPy and nusa offer minimal educational implementations. The recommended learning progression is: (1) build a 2D truss solver, (2) extend to 2D frames with rotational DOFs, (3) add loads between nodes via equivalent nodal loads, (4) implement geometric nonlinearity (P-Δ), (5) extend to 3D with 12×12 element matrices. Each step adds complexity incrementally and can be validated against existing tools.

## Conclusion

The structural analysis open-source landscape splits cleanly into tools that are powerful but hard to embed (OpenSees, CalculiX, Code_Aster) and tools that are embeddable but limited in scope (anastruct, pyCBA). **PyNite occupies the rare sweet spot** — embeddable, MIT-licensed, 3D-capable, and maintained by a practicing engineer. But the most strategically sound approach for a custom frame builder may be to **write your own solver core** (validated against PyNite or anastruct) and reserve the heavyweight packages as reference implementations or future swap-in options when advanced nonlinear capabilities are needed. The direct stiffness method for frames is well-understood, compact to implement, and the performance requirements for interactive use are easily met at any language level. The emerging Rust+WASM+modern-frontend pattern (exemplified by Stabileo) represents where this space is heading — and starting with that architecture now positions you well for both the 2D present and the 3D future.