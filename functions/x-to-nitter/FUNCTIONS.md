# Functions in `x-to-nitter.py`

## x_to_nitter
Converts a Twitter/X URL to its equivalent Nitter URL for privacy-friendly viewing.

**Signature:**
```python
def x_to_nitter(url: str, nitter_instance: str = "nitter.net") -> str
```

**Parameters:**
- `url` (str): The original Twitter/X URL to convert.
- `nitter_instance` (str, optional): The Nitter instance domain to use (default: `nitter.net`).

**Returns:**
- (str): The converted Nitter URL, or an error message if the input is invalid.

**Behavior:**
- Validates the input URL.
- Replaces the Twitter/X domain with the specified Nitter instance.
- Returns the Nitter URL for privacy-friendly, tracker-free access to public Twitter/X content.
