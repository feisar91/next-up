# Next Up documentation site

The pages in this folder are published with GitHub Pages (Settings > Pages > Deploy
from a branch > `main`, folder `/docs`). GitHub builds them with Jekyll; there's no
build step to run yourself.

- Pages are Markdown (`getting-started.md`, `guides/*.md`, `faq.md`) plus the home
  page, `index.html`. The sidebar comes from `_data/nav.yml`.
- `_config.yml` holds the GitHub repository name and the address the site is served
  from (`baseurl`). Change both if the repository is renamed or moved to a custom domain.
- Screenshots are in `assets/img` and the demo video in `assets/video`. Don't edit
  them by hand: they're made by `tools/build-media.sh`, which runs the app with the
  demo shop (`flask seed-demo`) and drives it with Playwright. Re-run it after
  changing how a screen looks:

  ```bash
  pip install -r docs/tools/requirements.txt && playwright install chromium
  docs/tools/build-media.sh
  ```

  It also makes `assets/social.png`, the picture shown when a link to the site is
  pasted into Facebook, Discord and so on (`tools/social-image.py`).

To preview the site locally with Docker:

```bash
docker run --rm -it -p 4000:4000 -v "$PWD/docs:/srv/jekyll" jekyll/jekyll:4.2.2 \
  jekyll serve --host 0.0.0.0 --baseurl ""
```

then open http://localhost:4000. Page edits show up when you reload, but changes to
`_config.yml` (such as the repository name) need the preview restarted.
