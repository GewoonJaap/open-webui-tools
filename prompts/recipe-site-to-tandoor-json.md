Scrape the URL and convert the recipe found on the website to a Tandoor JSON scheme, include an image URL aswell.
Note an instgram image url is like this: https://www.instagram.com/p/POSTID/media/?size=l
Example, post: https://www.instagram.com/pienlaathaaretenzien/p/DJBUi-8I3E1/ convert to image url: https://www.instagram.com/p/DJBUi-8I3E1/media/?size=l
 JSON scheme looks like this:

{
  "@context": "https://schema.org/",
  "@type": "Recipe",
  "name": "Rigatoni met Knapperige Chorizo en Champignon",
  "description": "Een smaakvolle pasta met rigatoni, knapperige chorizo en champignons, perfect voor een snelle maaltijd.",
  "image": "https://www.instagram.com/p/CiuGY3Ro4ho/media/?size=l",
  "author": {
    "@type": "Person",
    "name": "Pien laat haar eten zien"
  },
  "datePublished": "2022-09-15",
  "prepTime": "PT15M",
  "cookTime": "PT20M",
  "totalTime": "PT35M",
  "recipeYield": "2 porties",
  "recipeCategory": "Hoofdgerecht",
  "recipeCuisine": "Italiaans",
  "keywords": "rigatoni, chorizo, champignon, pasta",
  "recipeIngredient": [
    "200 gram rigatoni",
    "150 gram chorizo, in blokjes",
    "200 gram champignons, in plakjes",
    "1 ui, fijngehakt",
    "2 teentjes knoflook, fijngehakt",
    "200 ml kookroom",
    "50 gram Parmezaanse kaas, geraspt",
    "2 eetlepels olijfolie",
    "Zout en peper naar smaak",
    "Verse peterselie, gehakt (optioneel)"
  ],
  "recipeInstructions": [
    {
      "@type": "HowToStep",
      "text": "Kook de rigatoni volgens de aanwijzingen op de verpakking. Giet af en zet apart."
    },
    {
      "@type": "HowToStep",
      "text": "Verhit de olijfolie in een grote pan op middelhoog vuur. Voeg de blokjes chorizo toe en bak tot ze knapperig zijn. Haal de chorizo uit de pan en laat uitlekken op keukenpapier."
    },
    {
      "@type": "HowToStep",
      "text": "In dezelfde pan, voeg de fijngehakte ui toe en bak tot deze glazig is. Voeg de knoflook en plakjes champignons toe en bak tot de champignons zacht zijn."
    },
    {
      "@type": "HowToStep",
      "text": "Giet de kookroom in de pan en breng aan de kook. Voeg de geraspte Parmezaanse kaas toe en roer tot deze is gesmolten. Breng op smaak met zout en peper."
    },
    {
      "@type": "HowToStep",
      "text": "Voeg de gekookte rigatoni en de knapperige chorizo toe aan de saus. Meng goed zodat alle pasta bedekt is met de saus."
    },
    {
      "@type": "HowToStep",
      "text": "Serveer de pasta warm, eventueel gegarneerd met gehakte verse peterselie."
    }
  ],
  "nutrition": {
    "@type": "NutritionInformation",
    "calories": "750 kcal",
    "carbohydrateContent": "80 gram",
    "proteinContent": "30 gram",
    "fatContent": "35 gram"
  },
  "source": "https://www.instagram.com/p/CiuGY3Ro4ho/"
}
Reply in same language as user input

Recipe site: 
