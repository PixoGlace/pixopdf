# Design system

PixoPDF uses navy `#172B4D` for structure, teal `#14B8A6` for primary actions, amber `#F59E0B` for warnings, and red only for destructive/error states. Dark surfaces are `#0F172A`, `#111827`, `#1E293B`; light surfaces are `#F8FAFC`, white and `#F1F5F9`. Controls use an 8 px spacing rhythm, visible focus, keyboard navigation, sufficient contrast and concise accessible labels. The direction follows PixoCrop without code coupling; no sibling PixoCrop checkout was available during foundation work.

Page changes use a redundant color-and-text treatment: teal identifies a moved
page, while amber identifies an added or modified page. A visible badge, outline,
tooltip and legend ensure that color is never the only cue.
