# Demo food images

The 43 starter dishes use distinct, remotely hosted Unsplash food photography URLs. They are stored in `app/data/menu_seed.json` and loaded by `flask --app wsgi:app seed-menu`.

The URLs are high-resolution crop URLs with `w=900&q=82`. If a remote image fails, each product card and order card falls back to a clean generated placeholder.

The student navigation header uses `menu-hero-ingredients.png` as its background. The popular-dishes carousel retains its per-dish images.

Remote image source:
- https://unsplash.com/license
- https://unsplash.com
