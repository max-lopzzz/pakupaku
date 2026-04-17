# PakuPaku — Google Play Store Description

---

PakuPaku is an inclusive nutrition tracker built for every body. Whether you're counting calories, tracking macros, logging meals, or just trying to build a healthier relationship with food, PakuPaku gives you the tools to do it on your own terms — without judgment, without diet culture, and without a one-size-fits-all approach.

## Built for Everyone

Most nutrition apps were designed with a narrow idea of who uses them. PakuPaku wasn't. The app includes hormonal profile options that go beyond a binary male/female toggle, with dedicated support for people on estrogen or testosterone HRT. Calorie and macro targets are calculated using a continuous interpolation model that adjusts as your body changes over time — not a fixed formula that ignores where you actually are in your journey.

Body fat estimation uses the U.S. Navy tape-measure method with separate body shape options, so you can choose the formula that matches your actual body composition rather than being forced into a category that doesn't fit.

## Smart Nutrition Calculations

PakuPaku calculates your personalized nutrition targets using established scientific formulas, adapted for a wider range of bodies than most apps support.

- **Body fat %** is estimated using the U.S. Navy method, with male, female, blended, and HRT-duration-weighted options.
- **BMR (Basal Metabolic Rate)** is calculated using Mifflin-St Jeor for male and female physiology, Katch-McArdle for a sex-neutral lean-mass-based approach, and a smooth HRT interpolation model for people currently transitioning.
- **TDEE (Total Daily Energy Expenditure)** is calculated from your BMR and activity level, with five activity tiers from sedentary to extreme.
- **Macro targets** are set based on your goal, lean body mass, and calorie budget — not arbitrary percentages.

### Metabolic Condition Support

PakuPaku is one of the few nutrition apps that acknowledges that standard calorie math doesn't work the same way for everyone. The onboarding flow includes optional metabolic condition inputs that adjust your BMR estimate accordingly:

- Hypothyroidism (treated and untreated)
- Hyperthyroidism (treated and untreated)
- PCOS
- Type 1 Diabetes
- Cushing's Syndrome
- HIV/AIDS with wasting syndrome
- Cancer (active)
- Eating disorder history

Where a condition requires clinical guidance, the app flags it clearly and recommends consulting a registered dietitian rather than acting on the calculated number alone. Eating disorder history automatically disables weight loss goals and redirects to a maintenance target.

### Dietitian Bypass

Already working with a dietitian or other healthcare professional? You can skip the calculation entirely and enter your own custom calorie and macro goals directly. Your professional's guidance always takes priority.

### Safety Floors and Caps

PakuPaku enforces evidence-based safety limits on all calculated targets:

- Deficits are capped at 1,000 kcal/day to protect lean muscle mass.
- Surpluses are capped at 500 kcal/day to minimize excess fat gain.
- Calorie targets are never allowed to fall below your BMR.

If a requested pace would exceed these limits, the app explains why and adjusts automatically.

## Food Logging

Log your meals quickly using the USDA FoodData Central database — one of the most comprehensive food databases available, with hundreds of thousands of entries including branded foods.

- Search by food name or brand
- Log any amount in grams
- Track calories, protein, fat, carbohydrates, fiber, sugar, and sodium
- Label entries by meal (breakfast, lunch, dinner, snack, or anything you like)
- View a daily summary with totals and remaining targets for each macro
- Delete individual log entries at any time

## Custom Recipes

Build your own recipes and log them just like any other food.

- Add ingredients from the USDA database
- Set the number of servings
- PakuPaku automatically calculates per-serving nutrition totals
- Log a recipe serving directly from your recipe list
- Edit or delete recipes at any time

## Body Measurements

Track your body composition over time with a dedicated measurement log.

- Log weight, height, waist, neck, and hip measurements
- Body fat % is automatically recalculated from each new entry using your current body shape profile
- View your full measurement history in chronological order

## Apple Health Integration

On iOS, PakuPaku can optionally read active calories burned from Apple Health to help you understand your daily energy balance. This integration is entirely opt-in — the app will ask for permission through Apple's standard HealthKit prompt, and you can revoke access at any time from iOS Settings or the Health app.

## Safe Mode

Numbers aren't for everyone. Safe mode hides calorie figures throughout the app while keeping all other features fully functional. It's designed for users who find calorie counts triggering or counterproductive, and can be toggled on or off at any time from Settings.

## Your Data, Your Control

PakuPaku takes data ownership seriously.

- **Export your data** at any time from the Settings screen.
- **Delete your account** and all associated data instantly from within the app. No waiting period, no hoops to jump through.
- Your health data is never sold or shared with advertisers.
- Apple Health data is never transmitted off your device.

## Account and Security

- Accounts are secured with bcrypt password hashing and JWT-based authentication.
- Email verification is used to confirm account ownership.
- All data is transmitted over HTTPS.

---

PakuPaku is a wellness and nutrition support tool. It is not a medical device and is not intended to diagnose, treat, or replace the advice of a healthcare professional. If you have a medical condition affecting your nutrition needs, please consult a registered dietitian or your doctor.
