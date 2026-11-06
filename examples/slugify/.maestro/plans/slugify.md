# Plan: Slugify Helper (Task 004)

## Approach
Implement `slugify(text)` in `src/slugify.py`:
1. Validate input type: check `isinstance(text, str)`. If not a string, raise `TypeError("Input must be a string")`.
2. Convert text to lowercase with `text.lower()`.
3. Normalize characters, collapse separators, and preserve Unicode combining marks:
   - Iterate through characters of the lowercased text.
   - Keep a character if `ch.isalnum()` is True.
   - Keep a character if `unicodedata.category(ch)` is in `('Mn', 'Mc')` (non-spacing and spacing combining marks such as Arabic tanween, tashkeel, and harakat) AND it immediately follows a kept character (`prev_kept` is True).
   - Any other character (spaces, punctuation, symbols, and underscores `_`) acts as a separator: collapse consecutive separator characters into a single hyphen `-` (ensuring no consecutive hyphens in the accumulator).
   - Document explicitly in the function docstring that underscores `_` are treated as separators and collapsed into hyphens.
4. Strip leading and trailing hyphens: `slug = ''.join(out).strip('-')`.
5. Error handling: If `slug` is empty (e.g. input was `""`, `"!!!"`, `"---"`, `"   "`), raise `ValueError("nothing left to slug")`.
6. Return `slug`.

## Alternative Rejected and Reason
- **Regex `re.sub(r'[\W_]+', '-', text)`**:
  Rejected because Python's regex `\w` matches only alphanumeric characters and underscore, and does NOT match Unicode combining marks (categories `Mn` and `Mc`, such as Arabic tanween `ً` and tashkeel). This would cause `re.sub` to erroneously drop combining marks and split words at diacritics (e.g. `'مرحباً بك'` would become `'مرحبا-بك'`).
- **ASCII-only transliteration / stripping**:
  Rejected because acceptance criteria require preserving letters and digits from any script (including Arabic).

## Files
- `src/slugify.py` (implementation)
- `src/test_slugify.py` (unit tests)

## Named Tests for Acceptance Criteria
1. `test_slugify_basic_formatting`:
   - Validates lowercase conversion, collapsing spaces/punctuation/underscores to a single `-`, and stripping leading/trailing `-`.
   - Examples: `"  Hello, World!  "` → `"hello-world"`, `"test__slug--example"` → `"test-slug-example"`.
2. `test_slugify_multilingual_and_unicode_scripts`:
   - Validates that letters and digits from any script are preserved.
   - Example: `"مرحبا بالعالم 2"` → `"مرحبا-بالعالم-2"`.
3. `test_slugify_unicode_combining_marks`:
   - Validates that Unicode combining marks (`Mn` and `Mc` such as Arabic tanween) attached to kept characters are preserved.
   - Example: `"مرحباً بك"` → `"مرحباً-بك"`.
4. `test_slugify_empty_or_punctuation_only_raises_value_error`:
   - Validates that `slugify("")`, `slugify("!!!")`, `slugify("---")`, and `slugify("   ")` raise `ValueError`.
5. `test_slugify_non_string_argument_raises_type_error`:
   - Validates that passing a non-string argument (`None`, `123`, `[]`, etc.) raises `TypeError`.

## Applied Corrections (from Reviewer Checkpoint task-004-q2)
- Added explicit handling of Unicode combining marks (`Mn` and `Mc` when following a kept character) using `unicodedata.category` to preserve Arabic tanween and harakat.
- Added dedicated named test `test_slugify_unicode_combining_marks` checking `slugify('مرحباً بك') == 'مرحباً-بك'`.
- Noted in the plan and docstring that underscore `_` is treated as a separator.

## Steps
1. Update `.maestro/plans/slugify.md` with corrections.
2. Call `maestro_checkpoint` (project `<project>`, task_id `004`, kind `plan`, plan_path `.maestro/plans/slugify.md`) and wait for `APPROVED`.
3. Ensure directory `src` exists.
4. Create `src/test_slugify.py` (TDD Red phase).
5. Run acceptance test command `python -m unittest discover -s src` and verify failure (Red).
6. Create `src/slugify.py` implementing `slugify` with docstring explaining separator handling including underscore (TDD Green phase).
7. Run acceptance test command `python -m unittest discover -s src` and verify passing (Green).
8. Verify all acceptance criteria against test outputs.
9. Write report `.maestro/reports/task-004.done.md` LAST according to `.maestro/report-template.md`.
