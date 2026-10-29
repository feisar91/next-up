---
title: Metrics and history
lead: How busy you are, when, and who's doing the cuts. Admins open it from the Metrics link at the top.
next: { title: "Putting it online", url: /guides/server/ }
---

Pick a period at the top: the last 7, 14, 30 or 90 days. Days run midnight to midnight in the timezone set on the Settings tab.

{% include figure.html src="metrics.webp" alt="The Metrics page" %}

## The numbers across the top

| | |
|---|---|
| **Cuts** | Customers marked Complete. |
| **Avg. wait time** | From checking in to being called to the chair. |
| **Avg. time in chair** | From being called to being marked Complete. |
| **No-shows / removed** | Customers taken off the list before they were called. |
| **Asked for a barber** | How many customers picked a barber at the kiosk. |

Customers cleared overnight because nobody marked them done have no real time in the chair, so they're left out of the averages.

## The charts

- **Cuts per day**, so you can spot quiet days and busy weeks.
- **Busiest times**: check-ins by day of the week and hour, averaged over the period. Pick one shop or all of them together. Use it to plan who works when.
- **Cuts by barber** and **Time in chair by barber**.
- **Preferred barber demand**: how often customers asked for each barber by name, and how many of those ended up in that barber's chair rather than someone else's.
- **Cuts by location**.

{% include figure.html src="metrics-heatmap.webp" alt="The busiest times heatmap, darkest around lunchtime and late afternoon" caption="Darker squares are busier hours." %}

## Taking the data elsewhere

- **Download Visits (CSV)** gives one row per check-in in the period: shop, customer, the barber they asked for, who served them, what happened, the times, and the wait and time in the chair. It opens in Excel, Numbers or Google Sheets.
- **Print / Save as PDF** prints the page in a layout made for paper, including every shop's heatmap. Choose "Save as PDF" in the print window to keep a copy.

The CSV has customers' names in it, so treat it like any other customer list.
