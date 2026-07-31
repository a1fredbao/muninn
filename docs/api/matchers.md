# Matchers

Matchers are reusable answer-checking functions.  Instead of writing
custom regex for every question type, use the built-in `Matchers`
factories.

## Built-in Matchers

### `Matchers.exact(key)`

Exact match after stripping whitespace.

``` python
# record: {"name": "hydrogen"}
Matchers.exact("name")
# user types "hydrogen" → True
# user types "Hydrogen" → False
```

### `Matchers.exact_integer(key)`

Extract digits from the user input and compare as strings (after stripping non-digit characters from the input). Note: this is string-based comparison, so leading zeros are preserved (e.g., "007" != "7").

``` python
# record: {"num": 17}
Matchers.exact_integer("num")
# user types "  17  " → True
# user types "#17"    → True
# user types "18"     → False
```

### `Matchers.case_insensitive(key)`

Case-insensitive match after trimming whitespace.

``` python
# record: {"sym": "He"}
Matchers.case_insensitive("sym")
# user types "he" → True
# user types "HE" → True
```

### `Matchers.chinese_symbol_pair(key1, key2)`

Match "Chinese+symbol" or "symbol+Chinese" in either order, ignoring
whitespace.

``` python
# record: {"name": "氢", "sym": "H"}
Matchers.chinese_symbol_pair("name", "sym")
# user types "氢H"   → True
# user types "H氢"   → True
# user types "氢 H"  → True
```

### `Matchers.any_order(*keys)`

Match when all field values appear somewhere in the input, ignoring
non-alphanumeric characters and case. Only ASCII letters and digits are retained during normalization; Unicode characters are discarded.

``` python
# record: {"period": 4, "group": "IVB"}
Matchers.any_order("period", "group")
# user types "4 IVB" → True
# user types "IVB4"  → True
```

### `Matchers.custom(fn)`

Pass your own function `(data_item: dict, user_input: str) -> bool`.

``` python
def my_matcher(record, user_input):
    # custom logic
    return True

Matchers.custom(my_matcher)
```
