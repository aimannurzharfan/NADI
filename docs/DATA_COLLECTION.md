# Data collection protocol

How to collect labelled readings so the trained model's accuracy means something. Labels are entered on the **Calibration** page (`/calibration`, on a phone too; the old `/label` address opens it) and saved to `ml/data/labels.csv`.

## Before you start

- **Permission.** Only collect in a room you are allowed to use, with the agreement of everyone who will be in it. Tell them what is recorded: a headcount and Wi-Fi signal numbers, no images, no names. **Never collect at a workplace without written permission** from whoever is responsible for it. See [PRIVACY.md](../PRIVACY.md).
- **Boards fixed.** Sender and receiver 3 to 5 m apart, about 1 m high, across where people sit. Tape them down. **Do not move them** for the rest of the collection, or until the demo: moving them changes the readings.
- **Boards live.** Receiver LED green, dashboard shows the room. Readings from the simulator are never used for training, only those from real boards.

## Sessions

One **session** is about **5 minutes** with a fixed number of people in the room. Tap the count on the Calibration page when the session starts, and tap **Stop** when it ends (or tap the next count straight away).

| Headcount | Sessions | Activity |
|---|---|---|
| 0 (empty) | at least 2 | Nobody in the room, door closed |
| 1 | at least 2 sitting, at least 2 walking | One person sitting and working; one person walking around |
| 2 | at least 2 sitting, at least 2 walking | |
| 3+ | at least 2 sitting, at least 2 walking | Three or more people |

- Spread sessions over different times and days if you can (morning and afternoon, different people).
- Mix the order: do not always do 0, then 1, then 2.
- Between sessions, leave a minute unlabelled while people come in or leave.
- Write nothing else in the labels: no names, no notes about who was there.

## Training and testing

```powershell
powershell -ExecutionPolicy Bypass -File scripts\retrain.ps1
```

- The test set is made of **whole sessions held out**, not random rows: for each headcount, its latest sessions are kept back (about 20%, at least one when there are two or more). Readings within one session are near copies of each other, so testing on rows from a session the model has already seen would overstate the accuracy. The script prints how it split, for example `Train/test split by labelling session: 16 sessions to train, 4 held out to test (not random rows).`
- A headcount with only one session is used for training but cannot be tested; the script says so. Record at least two.
- The new model is used only if it was trained on real board readings **and** beats the calibrated threshold rule on the same held-out sessions. Report the held-out accuracy and confusion matrix, never the training accuracy.
