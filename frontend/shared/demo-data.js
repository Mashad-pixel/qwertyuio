(function () {
  const image = (id) => `https://images.unsplash.com/${id}?auto=format&fit=crop&w=900&q=82`;

  const demoData = {
    products: [
      { id: 1, name: "Masala Dosa", category: "Breakfast", price: 60, description: "Crisp dosa filled with spiced potato masala.", image: image("photo-1668236543090-82eba5ee5976"), isVeg: true, rating: 4.8, isPopular: true, isAvailable: true },
      { id: 2, name: "Idli Sambar", category: "Breakfast", price: 40, description: "Soft steamed idlis with warm lentil sambar.", image: image("photo-1589301760014-d929f3979dbc"), isVeg: true, rating: 4.5, isPopular: false, isAvailable: true },
      { id: 3, name: "Poori Bhaji", category: "Breakfast", price: 55, description: "Fluffy pooris served with potato bhaji.", image: image("photo-1596040033229-a9821ebd058d"), isVeg: true, rating: 4.6, isPopular: false, isAvailable: true },
      { id: 4, name: "Vegetable Upma", category: "Breakfast", price: 35, description: "Savory semolina cooked with vegetables.", image: image("photo-1630383249896-424e482df921"), isVeg: true, rating: 4.3, isPopular: false, isAvailable: true },
      { id: 5, name: "Paneer Paratha", category: "Breakfast", price: 70, description: "Whole-wheat paratha stuffed with seasoned paneer.", image: image("photo-1599487488170-d11ec9c172f0"), isVeg: true, rating: 4.7, isPopular: false, isAvailable: true },
      { id: 6, name: "Plain Dosa", category: "Breakfast", price: 45, description: "Thin, crisp golden rice and lentil dosa.", image: image("photo-1694849789325-914b71ab4075"), isVeg: true, rating: 4.4, isPopular: false, isAvailable: true },
      { id: 7, name: "Onion Uttapam", category: "Breakfast", price: 55, description: "Soft savory pancake topped with onions.", image: image("photo-1511690743698-d9d85f2fbf38"), isVeg: true, rating: 4.5, isPopular: false, isAvailable: true },
      { id: 8, name: "Pongal", category: "Breakfast", price: 50, description: "Comforting rice and moong dal porridge.", image: image("photo-1517673400267-0251440c45dc"), isVeg: true, rating: 4.4, isPopular: false, isAvailable: true },
      { id: 9, name: "Aloo Paratha", category: "Breakfast", price: 60, description: "Ghee-finished flatbread with spiced potato.", image: image("photo-1601050690117-94f5f6fa8bd7"), isVeg: true, rating: 4.6, isPopular: false, isAvailable: true },
      { id: 10, name: "Bread Omelette", category: "Breakfast", price: 45, description: "Golden omelette layered in buttered toast.", image: image("photo-1525351484163-7529414344d8"), isVeg: false, dietType: "egg", rating: 4.3, isPopular: false, isAvailable: true },

      { id: 11, name: "South Indian Veg Thali", category: "Lunch", price: 120, description: "Rice, sambar, vegetables, rasam and curd.", image: image("photo-1547592180-85f173990554"), isVeg: true, rating: 4.7, isPopular: true, isAvailable: true },
      { id: 12, name: "Chicken Biryani", category: "Lunch", price: 150, description: "Aromatic basmati rice cooked with tender chicken.", image: image("photo-1631515243349-e0cb75fb8d3a"), isVeg: false, rating: 4.9, isPopular: true, isAvailable: true },
      { id: 13, name: "Paneer Butter Masala", category: "Lunch", price: 130, description: "Paneer in a rich tomato, butter and cream gravy.", image: image("photo-1631452180519-c014fe946bc7"), isVeg: true, rating: 4.8, isPopular: true, isAvailable: true },
      { id: 14, name: "Veg Pulao", category: "Lunch", price: 90, description: "Fragrant rice with seasonal vegetables.", image: image("photo-1596797038530-2c107229654b"), isVeg: true, rating: 4.4, isPopular: false, isAvailable: true },
      { id: 15, name: "Dal Tadka Rice", category: "Lunch", price: 100, description: "Yellow dal with tempered spices and steamed rice.", image: image("photo-1546833999-b9f581a1996d"), isVeg: true, rating: 4.5, isPopular: false, isAvailable: true },
      { id: 16, name: "Egg Fried Rice", category: "Lunch", price: 100, description: "Wok-tossed rice with egg and vegetables.", image: image("photo-1603133872878-684f208fb84b"), isVeg: false, dietType: "egg", rating: 4.5, isPopular: false, isAvailable: true },
      { id: 17, name: "Chicken Fried Rice", category: "Lunch", price: 130, description: "Chicken, rice and vegetables tossed over high heat.", image: image("photo-1512058564366-18510be2db19"), isVeg: false, rating: 4.7, isPopular: false, isAvailable: true },
      { id: 18, name: "Veg Noodles", category: "Lunch", price: 90, description: "Noodles tossed with crunchy vegetables and sauces.", image: image("photo-1585032226651-759b368d7246"), isVeg: true, rating: 4.4, isPopular: false, isAvailable: true },
      { id: 19, name: "Chole Bhature", category: "Lunch", price: 90, description: "Spiced chickpeas with soft, fluffy bhature.", image: image("photo-1626132647523-66f5bf380027"), isVeg: true, rating: 4.8, isPopular: false, isAvailable: true },
      { id: 20, name: "Rajma Rice", category: "Lunch", price: 100, description: "Homestyle kidney beans curry with steamed rice.", image: image("photo-1600891964599-f61ba0e24092"), isVeg: true, rating: 4.6, isPopular: false, isAvailable: true },
      { id: 21, name: "Roti Combo", category: "Lunch", price: 110, description: "Fresh rotis with seasonal curry and salad.", image: image("photo-1585937421612-70a008356fbe"), isVeg: true, rating: 4.5, isPopular: false, isAvailable: true },

      { id: 22, name: "Samosa (2 pcs)", category: "Snacks", price: 30, description: "Two crisp pastries stuffed with spiced potato.", image: image("photo-1601050690597-df0568f70950"), isVeg: true, rating: 4.6, isPopular: false, isAvailable: true },
      { id: 23, name: "Pav Bhaji", category: "Snacks", price: 70, description: "Buttery pav with a flavorful vegetable mash.", image: image("photo-1606491956689-2ea866880c84"), isVeg: true, rating: 4.8, isPopular: true, isAvailable: true },
      { id: 24, name: "Veg Spring Rolls", category: "Snacks", price: 65, description: "Crunchy rolls filled with seasoned vegetables.", image: image("photo-1541745537411-b8046dc6d66c"), isVeg: true, rating: 4.3, isPopular: false, isAvailable: true },
      { id: 25, name: "Pani Puri", category: "Snacks", price: 40, description: "Crisp puris with potato and tangy spiced water.", image: image("photo-1529042410759-befb1204b468"), isVeg: true, rating: 4.7, isPopular: false, isAvailable: true },
      { id: 26, name: "French Fries", category: "Snacks", price: 70, description: "Golden crisp fries lightly seasoned with salt.", image: image("photo-1573080496219-bb080dd4f877"), isVeg: true, rating: 4.6, isPopular: true, isAvailable: true },
      { id: 27, name: "Veg Sandwich", category: "Snacks", price: 50, description: "Grilled sandwich layered with fresh vegetables.", image: image("photo-1528735602780-2552fd46c7af"), isVeg: true, rating: 4.4, isPopular: false, isAvailable: true },
      { id: 28, name: "Cheese Burger", category: "Snacks", price: 90, description: "Vegetable patty, cheese and fresh burger toppings.", image: image("photo-1568901346375-23c9450c58cd"), isVeg: true, rating: 4.7, isPopular: true, isAvailable: true },
      { id: 29, name: "Chicken Burger", category: "Snacks", price: 120, description: "Crispy chicken patty with cheese and sauces.", image: image("photo-1550547660-d9450f859349"), isVeg: false, rating: 4.6, isPopular: false, isAvailable: true },
      { id: 30, name: "Veg Momos", category: "Snacks", price: 70, description: "Steamed dumplings filled with seasoned vegetables.", image: image("photo-1626776876729-bab4369a5a5a"), isVeg: true, rating: 4.5, isPopular: false, isAvailable: true },
      { id: 31, name: "Chicken Momos", category: "Snacks", price: 90, description: "Juicy chicken dumplings served hot with chutney.", image: image("photo-1496116218417-1a781b1c416c"), isVeg: false, rating: 4.6, isPopular: false, isAvailable: true },
      { id: 32, name: "Onion Pakoda", category: "Snacks", price: 40, description: "Crispy onion fritters with gram flour coating.", image: image("photo-1574484284002-952d92456975"), isVeg: true, rating: 4.3, isPopular: false, isAvailable: true },
      { id: 33, name: "Bread Pizza", category: "Snacks", price: 80, description: "Toasted bread topped with cheese and vegetables.", image: image("photo-1574071318508-1cdbab80d002"), isVeg: true, rating: 4.4, isPopular: false, isAvailable: true },

      { id: 34, name: "Cold Coffee", category: "Drinks", price: 80, description: "Chilled creamy coffee with a frothy finish.", image: image("photo-1461023058943-07fcbe16d735"), isVeg: true, rating: 4.8, isPopular: true, isAvailable: true },
      { id: 35, name: "Mango Juice", category: "Drinks", price: 50, description: "Refreshing juice made from ripe mangoes.", image: image("photo-1623065422902-30a2d299bbe4"), isVeg: true, rating: 4.5, isPopular: false, isAvailable: true },
      { id: 36, name: "Masala Chai", category: "Drinks", price: 20, description: "Hot milk tea brewed with aromatic spices.", image: image("photo-1571934811356-5cc061b6821f"), isVeg: true, rating: 4.7, isPopular: false, isAvailable: true },
      { id: 37, name: "Fresh Lime Soda", category: "Drinks", price: 40, description: "Sparkling lime soda, sweet or salty.", image: image("photo-1513558161293-cdaf765ed2fd"), isVeg: true, rating: 4.4, isPopular: false, isAvailable: true },
      { id: 38, name: "Strawberry Milkshake", category: "Drinks", price: 70, description: "Creamy milkshake blended with strawberries.", image: image("photo-1579954115563-e72bf1381629"), isVeg: true, rating: 4.6, isPopular: false, isAvailable: true },
      { id: 39, name: "Sweet Lassi", category: "Drinks", price: 45, description: "Chilled sweetened yogurt drink.", image: image("photo-1556679343-c7306c1976bc"), isVeg: true, rating: 4.5, isPopular: false, isAvailable: true },
      { id: 40, name: "Buttermilk", category: "Drinks", price: 25, description: "Cooling spiced chaas with fresh herbs.", image: image("photo-1576091160399-112ba8d25d1d"), isVeg: true, rating: 4.3, isPopular: false, isAvailable: true },
      { id: 41, name: "Oreo Milkshake", category: "Drinks", price: 90, description: "Chocolate cookies blended with cold milk.", image: image("photo-1572490122747-3968b75cc699"), isVeg: true, rating: 4.7, isPopular: false, isAvailable: true },
      { id: 42, name: "Chocolate Milkshake", category: "Drinks", price: 80, description: "Rich chocolate milkshake topped with cream.", image: image("photo-1541658016709-82535e94bc69"), isVeg: true, rating: 4.6, isPopular: false, isAvailable: true },
      { id: 43, name: "Water Bottle", category: "Drinks", price: 20, description: "Chilled sealed packaged drinking water.", image: image("photo-1602143407151-7111542de6e8"), isVeg: true, rating: 4.2, isPopular: false, isAvailable: true }
    ],

    orders: [
      { id: "TY1001", items: [{ productId: 12, quantity: 1 }], total: 150, status: "Delivered" },
      { id: "TY1002", items: [{ productId: 1, quantity: 2 }], total: 120, status: "Preparing" },
      { id: "TY1003", items: [{ productId: 34, quantity: 1 }, { productId: 26, quantity: 1 }], total: 150, status: "On the way" },
      { id: "TY1004", items: [{ productId: 11, quantity: 1 }], total: 120, status: "Delivered" },
      { id: "TY1005", items: [{ productId: 22, quantity: 2 }], total: 30, status: "Cancelled" }
    ],

    sampleSales: [
      { period: "day", productId: 12, quantity: 24 },
      { period: "day", productId: 1, quantity: 21 },
      { period: "day", productId: 23, quantity: 18 },
      { period: "day", productId: 34, quantity: 16 },
      { period: "day", productId: 13, quantity: 14 },
      { period: "day", productId: 28, quantity: 12 },
      { period: "day", productId: 11, quantity: 10 },
      { period: "day", productId: 26, quantity: 9 },
      { period: "week", productId: 1, quantity: 138 },
      { period: "week", productId: 12, quantity: 126 },
      { period: "week", productId: 34, quantity: 102 },
      { period: "week", productId: 23, quantity: 96 },
      { period: "week", productId: 13, quantity: 83 },
      { period: "week", productId: 11, quantity: 76 },
      { period: "week", productId: 28, quantity: 68 },
      { period: "week", productId: 26, quantity: 59 },
      { period: "month", productId: 12, quantity: 514 },
      { period: "month", productId: 13, quantity: 468 },
      { period: "month", productId: 1, quantity: 441 },
      { period: "month", productId: 11, quantity: 386 },
      { period: "month", productId: 23, quantity: 354 },
      { period: "month", productId: 34, quantity: 329 },
      { period: "month", productId: 28, quantity: 298 },
      { period: "month", productId: 26, quantity: 247 }
    ]
  };

  const ingredientsByCategory = {
    Breakfast: ["Rice flour", "Lentils", "Potato", "Fresh herbs", "Spices"],
    Lunch: ["Basmati rice", "Seasonal vegetables", "Spices", "Ghee", "Fresh herbs"],
    Snacks: ["Fresh vegetables", "Flour", "Potato", "Spices", "Cooking oil"],
    Drinks: ["Fresh ingredients", "Milk or water", "Sugar", "Ice", "Natural flavors"]
  };

  const ingredientsByProduct = {
    1: ["Rice and lentils", "Potato", "Onion", "Mustard seeds", "Turmeric"],
    2: ["Rice", "Urad dal", "Toor dal", "Tomato", "Mixed vegetables"],
    3: ["Wheat flour", "Potato", "Onion", "Turmeric", "Cooking oil"],
    4: ["Semolina", "Carrot", "Green peas", "Curry leaves", "Mustard seeds"],
    5: ["Whole-wheat flour", "Paneer", "Green chili", "Coriander", "Garam masala"],
    6: ["Rice", "Urad dal", "Fenugreek seeds", "Salt", "Cooking oil"],
    7: ["Rice and lentil batter", "Onion", "Green chili", "Coriander", "Cooking oil"],
    8: ["Rice", "Moong dal", "Black pepper", "Cumin", "Ghee"],
    9: ["Whole-wheat flour", "Potato", "Cumin", "Coriander", "Ghee"],
    10: ["Egg", "Bread", "Onion", "Green chili", "Butter"],
    11: ["Rice", "Sambar", "Rasam", "Seasonal vegetables", "Curd"],
    12: ["Basmati rice", "Chicken", "Yogurt", "Onion", "Ginger and garlic"],
    13: ["Paneer", "Tomato", "Butter", "Cream", "Indian spices"],
    14: ["Basmati rice", "Carrot", "Green peas", "Whole spices", "Ghee"],
    15: ["Toor dal", "Rice", "Tomato", "Cumin", "Ghee"],
    16: ["Rice", "Egg", "Carrot", "Spring onion", "Soy sauce"],
    17: ["Rice", "Chicken", "Carrot", "Spring onion", "Soy sauce"],
    18: ["Noodles", "Cabbage", "Carrot", "Bell pepper", "Soy sauce"],
    19: ["Chickpeas", "Wheat flour", "Yogurt", "Tomato", "Chole masala"],
    20: ["Kidney beans", "Rice", "Tomato", "Onion", "Garam masala"],
    21: ["Whole-wheat flour", "Seasonal vegetables", "Tomato", "Onion", "Indian spices"],
    22: ["Potato", "Wheat flour", "Green peas", "Cumin", "Cooking oil"],
    23: ["Potato", "Cauliflower", "Green peas", "Tomato", "Onion", "Capsicum", "Ginger and garlic", "Pav bhaji masala", "Butter", "Pav bread", "Coriander", "Lemon", "Salt"],
    24: ["Spring roll wrapper", "Cabbage", "Carrot", "Bell pepper", "Soy sauce"],
    25: ["Puri", "Potato", "Chickpeas", "Mint", "Tamarind"],
    26: ["Potato", "Cooking oil", "Salt"],
    27: ["Bread", "Tomato", "Cucumber", "Onion", "Green chutney"],
    28: ["Burger bun", "Vegetable patty", "Cheese", "Lettuce", "Tomato"],
    29: ["Burger bun", "Chicken patty", "Lettuce", "Mayonnaise", "Seasoning"],
    30: ["Wheat flour", "Cabbage", "Carrot", "Onion", "Garlic"],
    31: ["Wheat flour", "Chicken", "Onion", "Ginger", "Garlic"],
    32: ["Onion", "Gram flour", "Carom seeds", "Chili powder", "Cooking oil"],
    33: ["Bread", "Tomato sauce", "Cheese", "Bell pepper", "Oregano"],
    34: ["Coffee", "Milk", "Sugar", "Ice", "Chocolate"],
    35: ["Mango", "Water", "Sugar", "Lime"],
    36: ["Tea leaves", "Milk", "Ginger", "Cardamom", "Sugar"],
    37: ["Lime", "Sparkling soda", "Black salt", "Sugar", "Mint"],
    38: ["Strawberries", "Milk", "Sugar", "Ice"],
    39: ["Yogurt", "Water", "Sugar", "Cardamom"],
    40: ["Yogurt", "Water", "Roasted cumin", "Mint", "Salt"],
    41: ["Chocolate sandwich cookies", "Milk", "Vanilla ice cream"],
    42: ["Milk", "Cocoa", "Sugar", "Chocolate ice cream"],
    43: ["Packaged drinking water"]
  };

  const historyByCategory = {
    Breakfast: "A comforting start inspired by traditional South Asian and Indian breakfast kitchens.",
    Lunch: "A wholesome, familiar meal shaped by regional Indian recipes and everyday cafeteria cooking.",
    Snacks: "Street-food favorites known for bold textures, fresh toppings and quick, shareable flavors.",
    Drinks: "Refreshing house beverages prepared to complement spicy meals and warm campus afternoons."
  };

  const foodHistory = {
    1: "Masala dosa grew from the dosa traditions of South India, where fermented rice-and-lentil batter is spread thin on a hot griddle. Its spiced potato filling became a much-loved variation, often served with coconut chutney and sambar.",
    2: "Idli and sambar are classic South Indian breakfast companions. Soft steamed idlis made from fermented rice and lentils pair with a tangy, vegetable-rich lentil stew that has become popular across India.",
    3: "Poori bhaji is a familiar North Indian combination of deep-fried puffed bread and gently spiced potato curry. It is enjoyed at breakfast and celebrations, with the contrast of crisp poori and soft bhaji at its heart.",
    4: "Upma is a home-style South Indian dish made by roasting semolina before cooking it with water and aromatics. Vegetables, curry leaves, mustard seeds and lentils add fragrance and texture to this quick, comforting meal.",
    5: "Stuffed parathas are a staple of North Indian home cooking. Paneer paratha brings fresh cheese, herbs and spices together inside whole-wheat dough, then cooks it on a griddle until golden.",
    6: "Plain dosa is made from a fermented rice-and-lentil batter and cooked into a thin, crisp crepe. Its simple flavor and delicate crunch make it a timeless South Indian favorite with chutney or sambar.",
    7: "Uttapam uses a thicker layer of fermented dosa batter and is topped with vegetables before it cooks. Onion uttapam is especially loved for its sweet, lightly charred onion topping and soft center.",
    8: "Pongal is a traditional Tamil comfort dish of rice and lentils cooked until soft and creamy. Pepper, cumin, ginger and ghee give the savory version its characteristic warmth.",
    9: "Aloo paratha is a North Indian flatbread filled with seasoned mashed potato. Rolled and toasted on a hot griddle, it is commonly served with yogurt, pickle or a little butter.",
    10: "Bread omelette is a popular quick meal from Indian street stalls and home kitchens. A spiced egg omelette is cooked with bread so the toast absorbs its savory flavor and gets crisp around the edges.",
    11: "The South Indian thali brings several regional staples together on one plate: rice, lentil dishes, vegetables, rasam, sambar and curd. A balanced variety of textures and flavors makes every portion feel like a complete meal.",
    12: "Biryani developed through centuries of Persian and South Asian culinary exchange, with regional styles evolving across the subcontinent. This version layers fragrant basmati rice with warmly spiced chicken for a celebratory, slow-cooked meal.",
    13: "Paneer butter masala is a modern North Indian restaurant classic. Paneer is simmered in a silky tomato-based gravy enriched with butter, cream and aromatic spices, then finished with herbs.",
    14: "Pulao is a one-pot rice dish with roots in the pilaf traditions that traveled through Central and South Asia. Indian versions bring together fragrant rice, whole spices and vegetables for a gently seasoned meal.",
    15: "Dal tadka is an everyday Indian favorite: lentils are simmered until tender and finished with a hot tempering of spices. Served with rice, it is simple, nourishing comfort food found in homes across the country.",
    16: "Fried rice became a beloved Indo-Chinese canteen dish, combining wok-tossed rice with vegetables, egg and savory sauces. High heat keeps the grains separate and adds a smoky, lightly toasted flavor.",
    17: "Chicken fried rice is a popular Indo-Chinese adaptation of wok-fried rice. Tender chicken, vegetables and rice are quickly tossed together so each bite gets a savory balance of seasoning and texture.",
    18: "Indian-style vegetable noodles draw on Indo-Chinese cooking, where noodles meet crisp vegetables, ginger, garlic and tangy sauces. Fast cooking over high heat keeps them lively and satisfying.",
    19: "Chole bhature is a much-loved North Indian pairing of chickpea curry and puffed fried bread. The chickpeas are slowly cooked with a robust spice blend, while the bhature arrive warm and airy.",
    20: "Rajma chawal is a Punjabi home-cooking staple of kidney beans simmered in a spiced tomato gravy and served with rice. Its slow-cooked, hearty character has made it comfort food throughout North India.",
    21: "Roti is a daily whole-wheat flatbread across many parts of India. This combo pairs fresh griddle-cooked rotis with a changing curry, making a familiar and flexible lunch.",
    22: "Samosas traveled through trade routes into the Indian subcontinent and became one of its best-known snacks. The crisp triangular pastry is filled here with spiced potato and served hot.",
    23: "Pav bhaji began as a filling, quick meal in Mumbai, where a spiced mash of vegetables was served with buttered bread rolls. Its rich bhaji, lemon and toasted pav remain a classic street-food combination.",
    24: "Spring rolls came to India through East Asian culinary influences and became a popular Indo-Chinese starter. A thin wrapper is filled with seasoned vegetables and fried until crisp.",
    25: "Pani puri is a beloved Indian street snack known by different names across regions. Crisp hollow puris are filled with potato or chickpeas and finished with tangy, spiced water just before eating.",
    26: "French fries became a global snack and are a familiar modern canteen favorite. The secret to a good serving is a crisp golden outside, a fluffy center and seasoning added while hot.",
    27: "The grilled vegetable sandwich is a familiar Indian bakery and street-café snack. Fresh vegetables, chutney and seasoning are tucked between bread and toasted until warm and crisp.",
    28: "The cheeseburger began as an American diner classic and has since been adapted around the world. This vegetarian version pairs a seasoned vegetable patty with melted cheese and fresh toppings in a toasted bun.",
    29: "The chicken burger is a modern fast-food favorite built around a seasoned chicken patty in a soft bun. Crisp lettuce, cheese and a balanced sauce make it a popular filling snack.",
    30: "Momos arrived in the Himalayan region through trade and migration and became especially popular in India’s northeast. These steamed dumplings wrap a finely seasoned vegetable filling in delicate dough.",
    31: "Chicken momos are a hearty variation of the Himalayan dumpling tradition. A savory chicken filling is sealed in thin dough and steamed, then served with a bright, spicy dipping chutney.",
    32: "Pakodas are a rainy-day favorite across India, made by coating vegetables in seasoned gram-flour batter and frying them crisp. Onion pakodas are prized for their lacy edges and sweet, tender center.",
    33: "Bread pizza is a quick home-style twist on Italian pizza, using bread as a crisp base for sauce, vegetables and cheese. It brings familiar pizza flavors to a simple, easy-to-share snack.",
    34: "Cold coffee became a café and college canteen staple as chilled coffee drinks spread across India. Blending coffee with cold milk creates a smooth, refreshing drink with a gentle roasted flavor.",
    35: "Mango juice celebrates India’s many mango varieties and the fruit’s short, eagerly awaited summer season. Ripe mango pulp makes a naturally fragrant drink enjoyed chilled.",
    36: "Masala chai grew from India’s long tea culture, with household spice blends varying from place to place. Strong tea is simmered with milk and warming spices for a fragrant everyday cup.",
    37: "Fresh lime soda is a refreshing Indian café classic, served sweet, salty or with both flavors together. Lime juice and sparkling soda make a bright counterpoint to spicy food.",
    38: "Fruit milkshakes became popular at Indian cafés as a chilled treat made with seasonal fruit and milk. Strawberries lend this version a sweet-tart flavor and a creamy finish.",
    39: "Lassi is a traditional Punjabi yogurt drink, served either savory or sweet. Sweet lassi is whisked until smooth and cooling, making it a popular partner for richly spiced meals.",
    40: "Buttermilk, or chaas, is a traditional cooling drink enjoyed across India. Yogurt is thinned and often seasoned with herbs, cumin or salt for a light, refreshing accompaniment.",
    41: "The Oreo milkshake is a modern café-style treat inspired by the familiar chocolate sandwich cookie. Crushed cookies blended with chilled milk make a rich, creamy drink.",
    42: "Chocolate milkshakes became a classic soda-fountain and café favorite. Chilled milk blended with chocolate creates a smooth, sweet drink served as an indulgent treat.",
    43: "Sealed bottled water is a convenient hydration choice for busy campus days. Chilled and ready to carry, it pairs simply with any meal."
  };

  const preparationByProduct = {
    1: "A gently fermented rice-and-lentil batter is spread into a thin circle on a hot griddle and cooked until crisp and golden. A savory potato filling is cooked separately with onion and spices, then tucked inside the dosa before serving.",
    2: "A fermented rice-and-urad-dal batter is poured into idli molds and steamed until the cakes are soft and fluffy. Toor dal, vegetables, tamarind and spices are simmered together to make the tangy sambar served alongside.",
    3: "Soft wheat dough is divided and rolled into small rounds, then fried until each poori puffs and turns golden. Potatoes are simmered with onion and spices into a tender bhaji that is served warm with the bread.",
    4: "Semolina is dry-roasted until fragrant, while mustard seeds, curry leaves and vegetables are sautéed separately. Hot water is stirred in with the semolina and cooked until the upma is tender, fluffy and savory.",
    5: "Crumbled paneer is seasoned with herbs and spices, then wrapped inside soft whole-wheat dough. The stuffed paratha is rolled gently and toasted on a hot griddle with ghee until both sides are golden.",
    6: "Rice-and-lentil batter is fermented to develop its light tang, then spread thinly over a lightly oiled hot griddle. The dosa cooks until its edges lift and the surface becomes crisp and golden.",
    7: "Fermented dosa batter is spread into a thick savory pancake and topped with onion, green chili and coriander. It is cooked slowly on a griddle so the center stays soft while the bottom turns lightly browned.",
    8: "Rice and moong dal are rinsed and simmered together until soft and creamy. A finishing tempering of ghee, cumin and black pepper adds the warm, savory aroma associated with pongal.",
    9: "Mashed potato is seasoned with cumin and coriander, sealed inside a round of whole-wheat dough and rolled carefully. The paratha is toasted on a hot griddle with ghee until its surface is crisp and golden.",
    10: "Eggs are whisked with onion, green chili and seasoning, then cooked in a pan until just set into a fluffy omelette. Bread is added and toasted with butter so the outside turns golden while the egg stays tender.",
    11: "Rice, sambar, rasam and seasonal vegetable dishes are cooked separately to keep their flavors distinct. They are arranged together with curd as a varied, balanced South Indian-style thali.",
    12: "Chicken is marinated with yogurt, ginger, garlic and spices while basmati rice is par-cooked with whole aromatics. The two are layered and sealed to steam slowly, allowing the rice to absorb the chicken juices and fragrance.",
    13: "Paneer cubes are gently simmered in a smooth tomato gravy seasoned with warming Indian spices. Butter and cream are stirred in near the end to create a rich, silky sauce without breaking the paneer.",
    14: "Seasonal vegetables and whole spices are sautéed to release their aroma before basmati rice is added. The rice cooks covered with measured water until fluffy and infused with the vegetable stock and spices.",
    15: "Toor dal is rinsed and simmered until soft, then lightly mashed to thicken the curry. A hot tempering of cumin and spices is poured over the dal, which is served with freshly steamed rice.",
    16: "Egg is scrambled with carrot and spring onion in a hot wok, then combined with cooked rice and savory seasoning. The mixture is tossed quickly over high heat so the grains stay separate and lightly smoky.",
    17: "Chicken is cut into small pieces and stir-fried until fully cooked, then set aside while vegetables are tossed over high heat. Cooked rice, chicken and seasoning are returned to the wok and mixed until hot throughout.",
    18: "Noodles are boiled until just tender, drained and kept ready while the vegetables are sliced. They are tossed in a hot wok with cabbage, carrot, pepper and sauce so they stay springy rather than soft.",
    19: "Chickpeas are soaked and cooked until tender, then simmered in an onion-tomato gravy with chole spices. Bhature dough is rolled and fried until puffed, and the hot bread is served alongside the thick curry.",
    20: "Kidney beans are soaked and cooked until creamy inside, then added to an onion-tomato masala with garam masala. The curry simmers until its sauce thickens and is served with steamed rice.",
    21: "Whole-wheat flour is kneaded with water into a soft dough, rested and rolled into thin rounds. Each roti is cooked on a hot griddle and served fresh with seasonal curry and salad.",
    22: "Potatoes and green peas are cooked with cumin and spices, then cooled for the filling. Thin pastry is shaped around the mixture and deep-fried until crisp and evenly golden.",
    23: "Potatoes, cauliflower and green peas are boiled until tender, then mashed on a hot griddle with butter. Onion, capsicum, ginger, garlic and tomatoes cook down with pav bhaji masala before the vegetables are folded in and simmered until the bhaji is thick, glossy and well seasoned. It is finished with butter, coriander and lemon, and served with pav toasted separately on the griddle.",
    24: "Cabbage, carrot and bell pepper are finely sliced and tossed with savory seasoning in a hot pan. The cooled filling is rolled tightly in thin wrappers and fried until the outside is crisp and golden.",
    25: "Potato and chickpeas are seasoned and spooned into crisp, hollow puris. Each puri is filled just before eating with mint and tamarind water so it stays crunchy and tangy.",
    26: "Potatoes are cut into even sticks and rinsed to remove excess surface starch, then dried well. They are fried until crisp and golden and seasoned with salt while still hot.",
    27: "Bread is spread with green chutney and layered with sliced tomato, cucumber and onion. The sandwich is pressed and toasted until the bread is crisp and the vegetable layers are warm.",
    28: "A seasoned vegetable patty is cooked on a hot griddle until crisp outside and heated through. It is placed in a toasted bun with cheese, lettuce and tomato, then served with the chosen sauces.",
    29: "A seasoned chicken patty is cooked until the center is fully done and the outside is crisp. It is layered in a soft toasted bun with lettuce, mayonnaise and other toppings before serving.",
    30: "Cabbage, carrot, onion and garlic are chopped finely, seasoned and wrapped in thin wheat dough. The dumplings are pleated closed and steamed until the wrappers are tender and the filling is hot.",
    31: "Minced chicken is mixed with onion, ginger, garlic and seasoning to make a savory filling. Small portions are wrapped in thin dough, pleated and steamed until the chicken is fully cooked.",
    32: "Onions are sliced and coated in a light gram-flour batter seasoned with carom seeds and chili. Small portions are dropped into hot oil and fried until crisp, then drained before serving.",
    33: "Bread is spread with tomato sauce and topped with chopped vegetables, cheese and oregano. It is toasted until the base is crisp and the cheese melts over the warm topping.",
    34: "Coffee is dissolved or brewed and cooled before blending with chilled milk, sugar and ice. The mixture is whipped until smooth and foamy, then poured cold into a glass.",
    35: "Ripe mango flesh is blended with cold water until smooth, with sugar added only as needed. A squeeze of lime brightens the flavor before the juice is served chilled.",
    36: "Tea leaves are simmered with ginger and cardamom so their flavor infuses the water. Milk and sugar are added, the chai is brought briefly to a boil, then strained hot into a cup.",
    37: "Fresh lime juice is mixed with sugar or salt and topped with chilled sparkling soda. The drink is stirred gently and served over ice so it keeps its fizz.",
    38: "Fresh strawberries are hulled and blended with chilled milk, sugar and ice. The shake is blended until creamy and smooth, then served immediately while cold.",
    39: "Yogurt is whisked until smooth, then blended with cold water, sugar and cardamom. The lassi is chilled and poured with a light frothy top.",
    40: "Yogurt is whisked with cold water until light and pourable, then seasoned with salt and roasted cumin. Mint is blended or stirred in before the chaas is served chilled.",
    41: "Chocolate sandwich cookies are crushed and blended with chilled milk and vanilla ice cream. The shake is mixed until creamy, with a few cookie pieces kept for texture if desired.",
    42: "Cocoa and sugar are blended with cold milk and chocolate ice cream until no dry cocoa remains. The shake is served immediately while thick and cold.",
    43: "The sealed drinking-water bottle is chilled without opening so it stays clean and ready to serve. It is presented cold as a simple accompaniment to any meal."
  };

  const recipeStepsByProduct = {
    1: [
      "Cook the potato masala with onion, mustard seeds and turmeric until the potatoes are soft and well seasoned.",
      "Pour a ladle of fermented batter onto a hot, lightly oiled griddle and spread it into a thin circle.",
      "Cook until crisp and golden, spoon the potato filling into the center, fold and serve warm."
    ],
    2: [
      "Blend soaked rice and urad dal into a smooth batter, mix and leave it to ferment until light and airy.",
      "Pour the batter into greased idli molds and steam until the cakes are fluffy and cooked through.",
      "Simmer cooked lentils with vegetables, tamarind and spices to make sambar, then serve it hot with the idlis."
    ],
    3: [
      "Knead wheat flour with water into a smooth dough, divide it into balls and roll each into a small round.",
      "Cook potatoes with onion and turmeric until tender, then lightly mash and season to make the bhaji.",
      "Fry each dough round until it puffs and turns golden, and serve immediately with the warm potato bhaji."
    ],
    4: [
      "Dry-roast the semolina in a pan until fragrant, then set it aside.",
      "Temper mustard seeds and curry leaves, add chopped vegetables and cook until they begin to soften.",
      "Stir in hot water and the semolina gradually; cook, stirring, until fluffy and serve warm."
    ],
    5: [
      "Mix crumbled paneer with green chili, coriander and garam masala for the filling.",
      "Place the filling inside a small round of whole-wheat dough, seal it and roll gently into a paratha.",
      "Toast on a hot griddle with ghee, turning until both sides are golden and the center is hot."
    ],
    6: [
      "Blend soaked rice and urad dal into a smooth batter, season lightly and leave it to ferment.",
      "Spread a ladle of batter thinly over a lightly oiled hot griddle.",
      "Cook until the edges are crisp and golden, then fold and serve hot."
    ],
    7: [
      "Spoon fermented batter onto a warm, lightly oiled griddle and shape it into a thick round.",
      "Scatter onion, green chili and coriander over the top, pressing them gently into the batter.",
      "Cook covered on low heat until set, flip briefly to brown the other side, then serve."
    ],
    8: [
      "Rinse the rice and moong dal, then simmer them together with water until very soft.",
      "Warm ghee in a small pan and toast cumin and black pepper until fragrant.",
      "Stir the tempering into the rice and dal, adjust the consistency and serve hot."
    ],
    9: [
      "Mash cooked potatoes with cumin and coriander to make a smooth, evenly seasoned filling.",
      "Enclose a portion of filling in whole-wheat dough, seal it and roll carefully into a flat round.",
      "Cook on a hot griddle with ghee, turning until both sides are golden and the filling is hot."
    ],
    10: [
      "Whisk eggs with chopped onion, green chili and seasoning until combined.",
      "Pour into a buttered pan and cook until the omelette is nearly set; place bread against it so it picks up the egg.",
      "Fold or layer the bread with the omelette and toast in butter until golden and cooked through."
    ],
    11: [
      "Cook rice until tender and prepare the sambar and rasam in separate pots.",
      "Cook the seasonal vegetables with their own seasoning and keep the curd chilled.",
      "Arrange rice, lentils, vegetables, rasam and curd together on a plate and serve warm."
    ],
    12: [
      "Marinate chicken with yogurt, ginger, garlic and spices; rinse and par-cook basmati rice with whole spices.",
      "Layer the chicken and rice in a heavy pot, adding aromatics between the layers, then cover tightly.",
      "Cook over low heat until the chicken is fully cooked and the rice is tender; rest briefly before serving."
    ],
    13: [
      "Cook tomatoes with onion and spices until soft, then blend into a smooth gravy.",
      "Simmer the gravy with butter and a little water, then add paneer and cook gently until heated through.",
      "Stir in cream, adjust the seasoning and serve the curry hot."
    ],
    14: [
      "Rinse basmati rice and chop the carrot and green peas; drain the rice well.",
      "Sauté whole spices and vegetables in ghee, then stir in the rice until lightly coated.",
      "Add water and salt, cover and cook on low heat until fluffy; rest before serving."
    ],
    15: [
      "Rinse toor dal and simmer it with water until completely soft, then lightly mash.",
      "Prepare a hot tempering with ghee, cumin and spices, and pour it over the cooked dal.",
      "Stir, adjust the consistency and seasoning, and serve with freshly steamed rice."
    ],
    16: [
      "Use cooled cooked rice and separate the grains; beat the egg and chop the vegetables.",
      "Scramble the egg in a hot wok, add carrot and spring onion, and stir-fry briefly.",
      "Add rice and soy sauce, toss over high heat until hot throughout, and serve."
    ],
    17: [
      "Cut the chicken into small pieces and stir-fry until fully cooked; set it aside.",
      "Cook carrot and spring onion quickly in a hot wok, then add cooled cooked rice.",
      "Return the chicken, season with soy sauce and toss until everything is hot throughout."
    ],
    18: [
      "Boil the noodles until just tender, drain and toss with a little oil to keep them separate.",
      "Stir-fry cabbage, carrot and bell pepper with garlic in a very hot wok.",
      "Add noodles and soy sauce, toss until heated through and serve while springy."
    ],
    19: [
      "Soak chickpeas, then pressure-cook or simmer them until tender.",
      "Cook tomato with onion and chole masala, add the chickpeas and simmer until the curry thickens.",
      "Roll bhature dough into rounds and fry until puffed; serve hot with the chickpea curry."
    ],
    20: [
      "Soak kidney beans and cook them until soft, then drain while keeping a little cooking liquid.",
      "Cook onion and tomato with garam masala, add the beans and simmer until the gravy thickens.",
      "Adjust seasoning and serve the rajma hot with steamed rice."
    ],
    21: [
      "Knead whole-wheat flour with water into a soft dough and let it rest briefly.",
      "Divide and roll the dough into thin rounds, then cook each on a hot griddle until lightly browned.",
      "Serve the fresh rotis with seasonal curry and salad."
    ],
    22: [
      "Cook potato and green peas with cumin and spices, then cool the filling completely.",
      "Shape pastry around a portion of filling into a sealed triangle.",
      "Fry in hot oil until crisp and golden, drain and serve warm."
    ],
    23: [
      "Boil the potatoes, cauliflower and green peas until tender. Drain them, then roughly mash the vegetables.",
      "Melt butter on a hot pan or griddle. Add chopped onion and cook until soft, then stir in ginger, garlic and capsicum until fragrant.",
      "Add chopped tomatoes, pav bhaji masala and salt. Cook, stirring, until the tomatoes soften and the spices smell aromatic.",
      "Mix in the mashed vegetables with a splash of water. Mash and simmer for 8–10 minutes, stirring until the bhaji is thick and evenly combined; adjust the seasoning.",
      "Finish with butter, chopped coriander and lemon juice. Split and butter-toast the pav until golden, then serve hot with the bhaji and lemon wedges."
    ],
    24: [
      "Shred cabbage, carrot and bell pepper, then stir-fry with soy sauce until tender-crisp; let the filling cool.",
      "Place filling on a wrapper, fold in the sides and roll tightly, sealing the edge with a little water.",
      "Fry the rolls until crisp and golden, drain and serve hot."
    ],
    25: [
      "Season cooked potato and chickpeas, then crack a small opening in the top of each puri.",
      "Fill each puri with the potato mixture and a little mint and tamarind chutney.",
      "Pour in chilled spiced water just before serving and eat immediately while crisp."
    ],
    26: [
      "Cut potatoes into even sticks, rinse away excess starch and dry them thoroughly.",
      "Fry the potatoes until tender, allow them to cool briefly, then fry again until crisp and golden.",
      "Drain and season with salt while hot; serve immediately."
    ],
    27: [
      "Spread green chutney on the bread and layer with sliced tomato, cucumber and onion.",
      "Close the sandwich and toast or grill it until the bread is crisp and the filling is warm.",
      "Cut into portions and serve while hot."
    ],
    28: [
      "Cook the vegetable patty on a hot griddle until crisp outside and hot in the middle.",
      "Toast the burger bun, then layer the patty with cheese, lettuce and tomato.",
      "Add sauces as desired, close the bun and serve immediately."
    ],
    29: [
      "Cook the chicken patty on a hot griddle or in an oven until fully cooked through.",
      "Toast the bun and layer it with lettuce, the chicken patty, cheese and mayonnaise.",
      "Close the burger and serve hot with the chosen sides."
    ],
    30: [
      "Finely chop cabbage, carrot, onion and garlic, then season and mix the vegetables.",
      "Add a small portion of filling to each dough wrapper, pleat the edges and seal securely.",
      "Steam until the wrappers are tender and the filling is hot; serve with chutney."
    ],
    31: [
      "Mix chicken with chopped onion, ginger, garlic and seasoning until evenly combined.",
      "Place a small portion on each dough wrapper, pleat the edges and seal the dumplings.",
      "Steam until the chicken filling is fully cooked and serve hot with chutney."
    ],
    32: [
      "Mix gram flour with carom seeds, chili powder and enough water to make a light batter.",
      "Coat the sliced onion, separate it into small clusters and carefully drop them into hot oil.",
      "Fry until crisp and golden, drain well and serve hot."
    ],
    33: [
      "Spread tomato sauce over the bread and add chopped bell pepper, cheese and oregano.",
      "Toast in a covered pan or oven until the bread is crisp and the cheese has melted.",
      "Cut into pieces and serve hot."
    ],
    34: [
      "Brew or dissolve the coffee, then cool it before blending.",
      "Blend coffee with chilled milk, sugar and ice until smooth and foamy.",
      "Pour into a cold glass and serve immediately."
    ],
    35: [
      "Peel and chop ripe mango, removing the stone.",
      "Blend the mango with cold water until smooth, adding sugar only if needed.",
      "Add a little lime juice, chill briefly and serve."
    ],
    36: [
      "Simmer tea leaves with crushed ginger and cardamom in water.",
      "Add milk and sugar, bring the chai briefly to a boil and stir.",
      "Strain into cups and serve hot."
    ],
    37: [
      "Squeeze fresh lime juice into a glass and stir in sugar or salt to taste.",
      "Add chilled sparkling soda and ice, then stir gently to retain the fizz.",
      "Serve immediately with a lime slice if desired."
    ],
    38: [
      "Wash, hull and slice the strawberries.",
      "Blend the fruit with chilled milk, sugar and ice until creamy and smooth.",
      "Pour into a chilled glass and serve immediately."
    ],
    39: [
      "Whisk the yogurt until smooth and loosen it with cold water.",
      "Blend in sugar and cardamom until lightly frothy.",
      "Chill and serve cold."
    ],
    40: [
      "Whisk yogurt with cold water until smooth and pourable.",
      "Stir in salt, roasted cumin and chopped mint.",
      "Chill briefly and serve as a refreshing accompaniment."
    ],
    41: [
      "Break the chocolate sandwich cookies into pieces.",
      "Blend the cookies with chilled milk and vanilla ice cream until thick and creamy.",
      "Pour into a cold glass and serve immediately."
    ],
    42: [
      "Whisk cocoa and sugar with a small splash of milk until smooth.",
      "Add the remaining cold milk and chocolate ice cream, then blend until creamy.",
      "Pour into a chilled glass and serve immediately."
    ],
    43: [
      "Check that the bottle is sealed and the packaging is intact.",
      "Chill the bottle until cold.",
      "Serve unopened until ready to drink."
    ]
  };

  demoData.products = demoData.products.map((product) => ({
    ...product,
    history: foodHistory[product.id] || historyByCategory[product.category],
    ingredients: ingredientsByProduct[product.id] || ingredientsByCategory[product.category],
    preparation: preparationByProduct[product.id],
    recipeSteps: recipeStepsByProduct[product.id] || []
  }));

  const activityKey = "trayup-order-activity";
  const ordersKey = "trayup-user-orders";

  function getActivity() {
    try {
      const saved = JSON.parse(localStorage.getItem(activityKey) || "null");
      if (Array.isArray(saved)) return saved;

      const now = new Date();
      const seeded = demoData.sampleSales.map((sale, index) => {
        const orderedAt = new Date(now);
        if (sale.period === "day") {
          orderedAt.setHours(Math.max(0, now.getHours() - 1), index % 60, 0, 0);
        } else if (sale.period === "week") {
          orderedAt.setDate(now.getDate() - (1 + (index % 6)));
        } else {
          orderedAt.setDate(now.getDate() - (8 + (index % 22)));
        }
        return {
          productId: sale.productId,
          quantity: sale.quantity,
          orderedAt: orderedAt.toISOString()
        };
      });
      localStorage.setItem(activityKey, JSON.stringify(seeded));
      return seeded;
    } catch (_) {
      return [];
    }
  }

  function nextReceiptNumber(orders) {
    const now = new Date();
    const day = String(now.getDate()).padStart(2, "0");
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const prefix = `${day}${month}`;
    let sequence = 0;

    orders.forEach((order) => {
      const createdAt = order.createdAt ? new Date(order.createdAt) : null;
      if (!createdAt || Number.isNaN(createdAt.getTime())) return;
      if (createdAt.getDate() !== now.getDate() || createdAt.getMonth() !== now.getMonth() || createdAt.getFullYear() !== now.getFullYear()) return;
      const match = String(order.id || "").match(new RegExp(`^${prefix}(\\d+)$`));
      if (match) sequence = Math.max(sequence, Number(match[1]));
    });

    return `${prefix}${sequence + 1}`;
  }

  demoData.getOrderActivity = getActivity;
  demoData.recordOrder = function (order) {
    const orders = JSON.parse(localStorage.getItem(ordersKey) || "[]");
    const savedOrder = {
      ...order,
      id: order.id || nextReceiptNumber(orders),
      createdAt: order.createdAt || new Date().toISOString()
    };
    orders.unshift(savedOrder);
    localStorage.setItem(ordersKey, JSON.stringify(orders));

    const activity = getActivity();
    savedOrder.items.forEach((entry) => {
      const productId = Number(entry.productId || entry.id);
      const quantity = Number(entry.quantity || entry.qty || 1);
      if (demoData.products.some((product) => product.id === productId) && quantity > 0) {
        activity.push({
          productId,
          quantity,
          orderedAt: savedOrder.createdAt,
          orderId: savedOrder.id
        });
      }
    });
    localStorage.setItem(activityKey, JSON.stringify(activity));
    return savedOrder;
  };

  window.trayDemoData = demoData;
})();
