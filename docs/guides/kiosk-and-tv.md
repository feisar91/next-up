---
title: Kiosk and TV
lead: Setting up the check-in tablet and the queue screen, and keeping them running.
next: { title: "Running the shop", url: /guides/admin/ }
---

## How the links work

Each shop has two links on the **Device Links** tab of the Admin page: one for the kiosk and one for the TV. Each link has a long random code in it, and the code is what lets a device in. Nobody logs in on these screens.

{% include figure.html src="admin-device-links.webp" alt="The Device Links tab" %}

That makes the links secret. Anyone with the kiosk link could add names to your queue, and anyone with the TV link could watch who's waiting. Keep them to the devices they're for.

If a link gets out, click **Regenerate** next to it. The old link stops working straight away, and any screen still open on it is disconnected. Then open the new link on the device.

## The kiosk

### What customers see

{% include figure.html src="kiosk.webp" size="tablet" alt="The check-in form" %}

<div class="shot-row">
{% include figure.html src="kiosk-group.webp" size="tablet" alt="Two names entered and a barber picked" caption="Up to six people can check in together, sharing a preferred barber." %}
{% include figure.html src="kiosk-confirmation.webp" size="tablet" alt="The confirmation screen with each person's place in line" caption="Each person gets their place in line. The screen resets after a few seconds." %}
</div>

- The barbers listed are the ones working at that shop right now. A barber on break, or one an admin has hidden from the kiosk, isn't listed.
- A name typed in and then left for a minute is cleared, so the next customer doesn't see it.
- When the shop is closed, the kiosk says so. If the shop follows [opening hours](../admin/#opening-hours), it also says when it opens next, for example "Back Tuesday at 9:00 am".

{% include figure.html src="kiosk-closed.webp" size="tablet" alt="The kiosk showing the shop is closed" caption="Closed by hand. With opening hours set, it also says when it opens next." %}

### Choosing and mounting a tablet

Any tablet with a current browser works: an iPad, or an Android tablet running Chrome. Portrait or landscape both work. A wall or counter mount with a charging cable keeps it in place and charged.

### Making it a full-screen app

Open the kiosk link on the tablet, then add it to the home screen: on an iPad, tap Share and then **Add to Home Screen**; in Chrome on Android, open the menu and tap **Add to Home screen**. Open it from the new icon. It runs without the browser's address bar, and the icon remembers its own link.

Android opens it truly full screen. iPads still show the status bar at the top. On Android, Chrome only opens it as an app when the site uses HTTPS. Over plain `http://` the icon opens an ordinary browser tab.

After regenerating a kiosk link, delete the icon and add it again from the new link.

### Stopping customers from leaving the app

Tablets can be locked to one app, so a customer can't wander off into the settings:

- **iPad**: turn on Guided Access (Settings, then Accessibility, then Guided Access), open the kiosk, and triple-click the side or home button to start it.
- **Android**: turn on app pinning (in Settings under Security, sometimes called screen pinning), open the kiosk, and pin it from the recent apps screen.

### Keeping the screen on

The kiosk and the TV ask the browser to keep the screen awake while they're open. Browsers only allow that over HTTPS, and some older ones don't support it at all. If the screen still dims, set the device's own sleep timer to never.

## The TV

{% include figure.html src="tv.webp" alt="The TV showing who's in the chair and who's waiting" %}

The TV shows who's in the chair and with which barber, then everyone waiting in order, with any barber they asked for. Names are cut down to a first name and initial ("Jordan S.") because the whole room can see it. Any announcement shows across the top.

Anything that can show a web page full screen will do:

- **A smart TV's own browser.** The cheapest option, though some TV browsers are slow or lose their place after the TV goes to standby.
- **A streaming stick or box** (Android TV, Fire TV) with a kiosk browser app that opens one page full screen at start-up.
- **A small PC or Raspberry Pi** plugged into the TV, running Chrome in kiosk mode: `chromium --kiosk <your TV link>`.

The TV doesn't need a keyboard or mouse once it's set up. It only shows things.

## Is it working?

The Device Links tab shows whether each screen is connected, and updates live:

| Status | Meaning |
|---|---|
| Online | The screen is open and connected. |
| Offline since 3:05 pm | It was connected and dropped off at that time. |
| Never connected | Nothing has opened this link yet. |
| Unknown | The app has just restarted and the screen hasn't reconnected yet. This turns into Online or Offline within a minute. |

A screen that's closed shows as offline after about 10 seconds. One that loses power or Wi-Fi without closing properly takes up to about 25 seconds. If two screens are open on the same link, the tab warns you.

Barbers see a note on their screen too when their shop's kiosk is offline, since that means customers can't check in.

## Things the screens do by themselves

- **Reconnect.** If the Wi-Fi drops, a red "Connection lost" bar shows until the screen is back. The kiosk holds its Check In button while the bar is up, so a customer can't send a name that would get lost.
- **Reload after changes.** After you update Next Up, or change the shop's name, colours or logo, open screens reload themselves. A kiosk waits until nobody is typing.
- **Clear overnight.** Customers still waiting or in the chair from the day before are cleared a few minutes after midnight. Waiting ones count as no-shows. Ones still in the chair count as done, without a time in the chair, so they don't skew the averages.
