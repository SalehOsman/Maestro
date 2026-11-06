CORRECTIONS. My previous answer reached you truncated: only its first line arrived, because of a
Maestro bug that is now fixed. These are the full corrections. Apply them, then call
maestro_checkpoint again.

1. [blocking] Combining marks are lost. In Python, `\w` does NOT match Unicode combining marks
   (categories Mn and Mc), such as Arabic tanween and harakat. Evidence, run on this machine:
     re.sub(r'[\W_]+', '-', 'مرحباً بك').strip('-')  ->  'مرحبا-بك'
     unicodedata.category('ً') == 'Mn';  'ً'.isalnum() is False;  re.match(r'\w', 'ً') is None
   The tanween becomes part of a separator run and is dropped. Keep a character when
   `ch.isalnum()` is true, or when `unicodedata.category(ch)` is 'Mn' or 'Mc' and it follows a
   kept character. Collapse every other run into a single '-', then strip '-' from both ends.
2. [blocking] Add a named test for this case: slugify('مرحباً بك') == 'مرحباً-بك'.
   Keep the existing case 'مرحبا بالعالم 2' -> 'مرحبا-بالعالم-2'.
3. [note] Treating underscore as a separator is fine. Say so in the docstring.

Review depth stays quick, because no high-risk area is touched.
