# django-bikram — renamed

This project is now **[django-bikram-sambat](https://pypi.org/project/django-bikram-sambat/)**.

```bash
pip uninstall django-bikram
pip install django-bikram-sambat
```
```python
from django_bikram_sambat import BSDate     # was: django_bikram
```

Same API, same calendar data, same behaviour — the rename spells out the
calendar, because "Bikram" alone is a common Nepali given name.

This package re-exports the new one so existing code keeps working, but it
receives no further releases.
