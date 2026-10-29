---
title: Your name, colours and logo
lead: Make the kiosk, TV and barbers' screens look like your shop rather than like Next Up.
next: { title: "Metrics and history", url: /guides/metrics/ }
---

Everything here is on the **Branding** tab of the Admin page. Changes show on open kiosks, TVs and barbers' screens within a few seconds, so you can try things with the kiosk open next to you.

{% include figure.html src="admin-branding.webp" alt="The Branding tab with a shop name, two colours, a logo and an icon" %}

## Shop name

Used in page titles, in the kiosk's header when there's no logo, as the name under the app's icon on home screens, and in the name of the visits file you can download from Metrics.

## Colours

You pick two:

- **Dark colour**: the headers, the kiosk and TV backgrounds, and most of the text.
- **Accent colour**: buttons, highlights, queue numbers and the charts.

The small preview under them shows how they look together before you save. **Use Default Colours** puts back the Next Up teal.

White writing has to be readable on both, so very light colours are refused with a note saying why. If your brand colour is pale, use a deeper shade of it for the accent. Warnings and errors stay red whatever you choose, so they always stand out.

## Logo

Shown large at the top of the kiosk. It's also used in the barbers' header and on the TV if you haven't added an icon.

The logo sits on your dark colour, so upload a white or light version. A PNG with a transparent background works best. JPEG and WebP are fine too, up to 5 MB. Transparent space around the edges is trimmed off.

<div class="shot-row">
{% include figure.html src="kiosk.webp" size="tablet" alt="The kiosk with the default colours and no logo" caption="No logo, default colours: the kiosk shows the shop name." %}
{% include figure.html src="kiosk-branded.webp" size="tablet" alt="The kiosk with a logo and orange buttons" caption="With a logo, navy and orange." %}
</div>

{% include figure.html src="tv-branded.webp" alt="The TV in the same navy and orange, with the shop's icon in the corner" caption="The TV in the same colours, with the icon beside the location name." %}

## Icon

A small square picture for browser tabs and home-screen icons, and for beside the shop name in the barbers' header and on the TV. A square version of your logo, or just its first letter, works well.

If you don't add one, the app uses your logo, shrunk to fit. With no logo either, it uses the Next Up chevrons in your colours.

Phones and tablets that already have the app on their home screen may keep the old icon. Remove the icon from the home screen and add it again to update it.

## Setting it from the command line

If you set up shops for other people, you can do all of this from a terminal instead:

```bash
docker compose exec app flask set-branding --name "Harbour Lane Barbers" --dark "#1d2b3a" --accent "#b45309"

docker compose cp logo.png app:/tmp/logo.png
docker compose exec app flask set-branding --logo /tmp/logo.png
```

Run `docker compose exec app flask set-branding --help` for every option. Screens that are already open pick up command-line changes the next time they reconnect, or when reloaded.
