"""Die Sprachen von Aquaticy Standard (16.4.2) -- gelesen von aquaticy/weltsprachen.py.

Eine Sprache beginnt mit ``@code Name | wiki=xx | schrift=latin`` (``nospace`` fuer Schriften
ohne Leerzeichen zwischen Woertern). Danach je Zeile ``feld = wert; wert; ...``; eine Zeile, die
mit zwei Leerzeichen beginnt, setzt die vorige fort. Listen: hallo, info (wer bist du / was
kannst du), danke, tschuess, wiegehts, wetter, zeit, datum, heute, morgen, wiki (``{x}`` ist das
Thema), stopp (kleine Woerter, die nicht zum Ort gehoeren), krise, endungen. Antworten stehen in
``A.feld``; ``{zeit}``, ``{datum}`` und ``{x}`` werden ersetzt. Die Reihenfolge folgt grob der
Zahl der Sprecher: Bei Gleichstand gewinnt die Sprache weiter oben.
"""

DATEN = """
@de Deutsch | wiki=de | schrift=latin
hallo = hallo; hi; hey; guten morgen; guten tag; guten abend; servus; moin; grüß dich
info = wer bist du; was kannst du; hilfe
danke = danke; danke schön; vielen dank; dankeschön
tschuess = tschüss; auf wiedersehen; bis bald; gute nacht
wiegehts = wie geht es dir; wie geht's; wie gehts
wetter = wetter; wettervorhersage; temperatur; regnet; regen; schnee; gewitter; nebel; hagel; sturm
zeit = wie spät ist es; uhrzeit; wie viel uhr
datum = welches datum; welcher tag ist heute; datum
heute = heute
morgen = morgen
wiki = was ist {x}; wer ist {x}; wer war {x}
stopp = in; im; für; das; der; die; wie; ist; wird; es; heute; morgen
krise = umbringen; suizid; sterben will

@en English | wiki=en | schrift=latin
hallo = hello; hi; hey; good morning; good evening; good afternoon; hello there
info = who are you; what can you do; help; what are you; what do you do
danke = thanks; thank you; thank you very much; thanks a lot; many thanks
tschuess = bye; goodbye; see you; see you later; good night
wiegehts = how are you; how are you doing; how is it going; how's it going
wetter = weather; forecast; temperature; raining; weather forecast; will it rain;
  going to rain; going to snow; is it snowing; will it snow; how cold; how hot; is it sunny;
  is it windy; what should i wear; what to wear; need an umbrella; take an umbrella;
  bring an umbrella
zeit = what time is it; current time; the time; time now
datum = what is the date; what's the date; today's date; what day is it; what date is it
heute = today
morgen = tomorrow
wiki = what is {x}; what are {x}; who is {x}; who was {x}; tell me about {x}; what's {x}
stopp = in; at; for; the; a; of; what; what's; whats; is; how; will; it; be; me; please;
  show; tell; like; today; tomorrow; now; current; going; to; there; do; i; need; an;
  should; this; weekend; snowing; raining; and
krise = kill myself; suicide; want to die; end my life; take my own life
A.intro = Hello! I'm Aquaticy Standard. I can tell you the weather, the time and the date,
  do calculations and look things up on Wikipedia.
A.danke = You're welcome!
A.tschuess = Goodbye! See you soon.
A.wiegehts = I'm fine, thanks! How can I help you?
A.zeit = It is {zeit}.
A.datum = Today is {datum}.
A.ort = For which place should I check the weather?
A.nichts = Sorry, I couldn't find anything about “{x}”.
A.rueckfall = Sorry, I can't answer that without a language model. Ask me about the weather,
  the time, the date, a calculation or something on Wikipedia.
A.krise = You are not alone. If you are thinking about ending your life, please talk to
  someone now: call your local emergency number or find a free helpline at
  https://findahelpline.com.

@zh 中文 | wiki=zh | schrift=han | nospace
hallo = 你好; 您好; 嗨; 早上好; 晚上好; 大家好; 哈喽
info = 你是谁; 你能做什么; 帮助; 你会什么; 你可以做什么
danke = 谢谢; 多谢; 谢谢你; 感谢; 谢了
tschuess = 再见; 拜拜; 晚安; 回头见
wiegehts = 你好吗; 最近怎么样; 你怎么样; 你还好吗
wetter = 天气; 天氣; 气温; 下雨; 天气预报
zeit = 现在几点; 几点了; 几点; 现在时间; 时间
datum = 今天几号; 几号; 日期; 星期几; 今天是几月几号
heute = 今天
morgen = 明天
wiki = {x}是什么; 什么是{x}; {x}是谁; 谁是{x}; 介绍一下{x}
stopp = 的; 怎么样; 如何; 吗; 呢; 今天; 明天; 现在; 请问; 请; 在; 了; 会; 吧; 啊
krise = 自杀; 想死; 不想活; 结束生命
A.intro = 你好！我是 Aquaticy Standard。我可以告诉你天气、时间和日期，帮你计算，
  还能在维基百科上查资料。
A.danke = 不客气！
A.tschuess = 再见！
A.wiegehts = 我很好，谢谢！有什么可以帮你的吗？
A.zeit = 现在是 {zeit}。
A.datum = 今天是 {datum}。
A.ort = 你想查哪个地方的天气？
A.nichts = 抱歉，关于“{x}”我没有找到相关信息。
A.rueckfall = 抱歉，没有语言模型我无法回答这个问题。你可以问我天气、时间、日期、计算
  或维基百科上的内容。
A.krise = 你并不孤单。如果你有结束生命的念头，请马上联系别人：拨打当地的紧急电话，
  或在 https://findahelpline.com 找到免费的求助热线。

@hi हिन्दी | wiki=hi | schrift=devanagari
hallo = नमस्ते; नमस्कार; हेलो; हाय; सुप्रभात; शुभ संध्या
info = तुम कौन हो; आप कौन हैं; तुम क्या कर सकते हो; आप क्या कर सकते हैं; मदद
danke = धन्यवाद; शुक्रिया; बहुत धन्यवाद; थैंक यू
tschuess = अलविदा; फिर मिलेंगे; बाय; शुभ रात्रि
wiegehts = आप कैसे हैं; तुम कैसे हो; क्या हाल है; कैसे हो
wetter = मौसम; तापमान; बारिश; मौसम का हाल
zeit = क्या समय हुआ है; कितने बजे हैं; समय क्या है; टाइम क्या है; समय
datum = आज कौन सी तारीख है; आज की तारीख; तारीख; आज कौन सा दिन है
heute = आज
morgen = कल
wiki = {x} क्या है; {x} कौन है; {x} कौन था; {x} के बारे में बताओ
stopp = में; का; की; के; क्या; है; हैं; कैसा; कैसी; रहेगा; होगा; आज; कल; बताओ; बताइए;
  का हाल; अभी
krise = आत्महत्या; मरना चाहता; मरना चाहती; खुद को मार
A.intro = नमस्ते! मैं Aquaticy Standard हूँ। मैं आपको मौसम, समय और तारीख बता सकता हूँ,
  हिसाब लगा सकता हूँ और विकिपीडिया पर जानकारी खोज सकता हूँ।
A.danke = आपका स्वागत है!
A.tschuess = अलविदा! फिर मिलेंगे।
A.wiegehts = मैं ठीक हूँ, धन्यवाद! मैं आपकी क्या मदद कर सकता हूँ?
A.zeit = अभी {zeit} बजे हैं।
A.datum = आज {datum} है।
A.ort = किस जगह का मौसम देखूँ?
A.nichts = माफ़ कीजिए, “{x}” के बारे में मुझे कुछ नहीं मिला।
A.rueckfall = माफ़ कीजिए, भाषा मॉडल के बिना मैं इसका जवाब नहीं दे सकता। मुझसे मौसम, समय,
  तारीख, हिसाब या विकिपीडिया के बारे में पूछिए।
A.krise = आप अकेले नहीं हैं। अगर आपके मन में अपनी जान लेने के विचार आ रहे हैं, तो अभी किसी से
  बात करें: अपने स्थानीय आपातकालीन नंबर पर कॉल करें या https://findahelpline.com पर
  मुफ़्त हेल्पलाइन खोजें।

@es Español | wiki=es | schrift=latin
zeichen = ñ;¿;¡
hallo = hola; buenos días; buenas tardes; buenas noches; saludos; buenas
info = quién eres; qué puedes hacer; ayuda; qué eres; qué sabes hacer
danke = gracias; muchas gracias; mil gracias; te lo agradezco
tschuess = adiós; hasta luego; chao; nos vemos; hasta pronto; hasta mañana
wiegehts = cómo estás; qué tal; cómo te va; cómo está usted
wetter = tiempo hace; qué tiempo; el tiempo; tiempo; clima; pronóstico; temperatura; llueve; lluvia;
  llover; lloverá; nevar; nieva; hará frío; hará calor; hace frío; hace calor
zeit = qué hora es; la hora; hora actual
datum = qué día es hoy; qué fecha es; la fecha; fecha de hoy
heute = hoy
morgen = mañana
wiki = qué es {x}; quién es {x}; quién fue {x}; qué son {x}; háblame de {x}
stopp = en; de; para; el; la; los; las; qué; que; hace; hará; cómo; como; es; está; va; a;
  hoy; mañana; tiempo; me; dime; por; favor; ahora; llover; lloverá; nevar; nieva; frío; calor;
  y
krise = suicidarme; quiero morir; matarme; quitarme la vida; suicidio
A.intro = ¡Hola! Soy Aquaticy Standard. Puedo decirte el tiempo, la hora y la fecha,
  hacer cálculos y buscar en Wikipedia.
A.danke = ¡De nada!
A.tschuess = ¡Adiós! Hasta pronto.
A.wiegehts = ¡Muy bien, gracias! ¿En qué puedo ayudarte?
A.zeit = Son las {zeit}.
A.datum = Hoy es {datum}.
A.ort = ¿Para qué lugar quieres saber el tiempo?
A.nichts = Lo siento, no encontré nada sobre «{x}».
A.rueckfall = Lo siento, sin un modelo de lenguaje no puedo responder a eso. Pregúntame por el
  tiempo, la hora, la fecha, un cálculo o algo de Wikipedia.
A.krise = No estás solo. Si estás pensando en quitarte la vida, habla con alguien ahora:
  llama al número de emergencias de tu país o busca una línea de ayuda gratuita en
  https://findahelpline.com.

@fr Français | wiki=fr | schrift=latin
zeichen = œ;ê;è
hallo = bonjour; salut; bonsoir; coucou; allô
info = qui es-tu; qui êtes-vous; que peux-tu faire; aide; tu sais faire quoi
danke = merci; merci beaucoup; merci bien; je te remercie
tschuess = au revoir; à bientôt; salut à plus; bonne nuit; à plus tard; adieu
wiegehts = comment ça va; ça va; comment vas-tu; comment allez-vous
wetter = météo; quel temps; le temps; température; pleut; prévisions;
  pleuvoir; pleuvra; neiger; neige; fait froid; fait chaud; fait beau
zeit = quelle heure est-il; quelle heure; l'heure
datum = quelle est la date; quel jour sommes-nous; la date; quel jour on est
heute = aujourd'hui
morgen = demain
wiki = qu'est-ce que {x}; qu'est-ce qu'un {x}; qu'est-ce qu'une {x}; qui est {x}; qui était {x};
  parle-moi de {x}
stopp = à; a; en; au; aux; de; du; la; le; les; quel; quelle; fait; il; fera; est; va;
  aujourd'hui; demain; pour; comment; temps; me; dis; donne; fait-il; fera-t-il; va-t-il;
  pleuvoir; pleuvra; neiger; neige; est-ce; qu'il; froid; chaud; beau; et
krise = me suicider; envie de mourir; me tuer; mettre fin à ma vie; suicide
A.intro = Bonjour ! Je suis Aquaticy Standard. Je peux te donner la météo, l'heure et la date,
  faire des calculs et chercher sur Wikipédia.
A.danke = De rien !
A.tschuess = Au revoir ! À bientôt.
A.wiegehts = Je vais bien, merci ! Comment puis-je t'aider ?
A.zeit = Il est {zeit}.
A.datum = Nous sommes le {datum}.
A.ort = Pour quel lieu veux-tu la météo ?
A.nichts = Désolé, je n'ai rien trouvé sur « {x} ».
A.rueckfall = Désolé, sans modèle de langage je ne peux pas répondre à cela. Demande-moi la
  météo, l'heure, la date, un calcul ou quelque chose sur Wikipédia.
A.krise = Tu n'es pas seul. Si tu penses à mettre fin à tes jours, parle à quelqu'un
  maintenant : appelle le numéro d'urgence de ton pays ou trouve une ligne d'écoute gratuite
  sur https://findahelpline.com.

@ar العربية | wiki=ar | schrift=arabic
hallo = مرحبا; مرحباً; السلام عليكم; أهلا; أهلاً; صباح الخير; مساء الخير; هلا
info = من أنت; ماذا تستطيع أن تفعل; ماذا يمكنك أن تفعل; مساعدة; ساعدني
danke = شكرا; شكراً; شكرا جزيلا; شكراً جزيلاً; مشكور
tschuess = مع السلامة; وداعا; إلى اللقاء; تصبح على خير; باي
wiegehts = كيف حالك; كيفك; شلونك; ازيك; كيف الحال
wetter = الطقس; طقس; حالة الطقس; درجة الحرارة; الجو; المطر
zeit = كم الساعة; الساعة كم; ما الوقت; الوقت الآن
datum = ما التاريخ; تاريخ اليوم; ما هو اليوم; أي يوم اليوم
heute = اليوم
morgen = غدا
wiki = ما هو {x}; ما هي {x}; من هو {x}; من هي {x}; من كان {x}; ما هو ال{x}
stopp = في; ب; ل; عن; ما; هو; هي; كيف; سيكون; اليوم; غدا; غداً; الآن; من; فضلك; لو; سمحت
krise = انتحار; أنتحر; أريد أن أموت; اقتل نفسي; أقتل نفسي
vorsilben = ب; ل; و; ال
A.intro = مرحباً! أنا Aquaticy Standard. أستطيع أن أخبرك بالطقس والوقت والتاريخ، وأن أحسب لك،
  وأن أبحث في ويكيبيديا.
A.danke = عفواً!
A.tschuess = مع السلامة! إلى اللقاء.
A.wiegehts = أنا بخير، شكراً! كيف يمكنني مساعدتك؟
A.zeit = الساعة الآن {zeit}.
A.datum = اليوم هو {datum}.
A.ort = لأي مكان تريد معرفة الطقس؟
A.nichts = عذراً، لم أجد شيئاً عن «{x}».
A.rueckfall = عذراً، لا أستطيع الإجابة عن ذلك بدون نموذج لغوي. اسألني عن الطقس أو الوقت أو
  التاريخ أو عملية حسابية أو شيء من ويكيبيديا.
A.krise = لست وحدك. إذا كنت تفكر في إنهاء حياتك، تحدث مع أحد الآن: اتصل برقم الطوارئ في
  بلدك أو ابحث عن خط مساعدة مجاني على https://findahelpline.com.

@bn বাংলা | wiki=bn | schrift=bengali
hallo = নমস্কার; হ্যালো; আসসালামু আলাইকুম; শুভ সকাল; শুভ সন্ধ্যা; হাই
info = তুমি কে; আপনি কে; তুমি কী করতে পারো; আপনি কী করতে পারেন; সাহায্য
danke = ধন্যবাদ; অনেক ধন্যবাদ; থ্যাংক ইউ
tschuess = বিদায়; আবার দেখা হবে; শুভ রাত্রি; বাই
wiegehts = কেমন আছো; কেমন আছেন; কী খবর
wetter = আবহাওয়া; তাপমাত্রা; বৃষ্টি
zeit = কয়টা বাজে; এখন কয়টা বাজে; সময় কত; সময়
datum = আজ কত তারিখ; আজকের তারিখ; তারিখ; আজ কী বার
heute = আজ
morgen = আগামীকাল
wiki = {x} কী; {x} কি; {x} কে; {x} সম্পর্কে বলো
stopp = এ; তে; য়; এর; কেমন; কী; কি; হবে; আজ; আগামীকাল; কাল; বলো; বলুন; এখন
krise = আত্মহত্যা; মরে যেতে চাই; নিজেকে মেরে
A.intro = নমস্কার! আমি Aquaticy Standard। আমি আপনাকে আবহাওয়া, সময় ও তারিখ জানাতে পারি,
  হিসাব করতে পারি এবং উইকিপিডিয়ায় খুঁজতে পারি।
A.danke = আপনাকে স্বাগতম!
A.tschuess = বিদায়! আবার দেখা হবে।
A.wiegehts = আমি ভালো আছি, ধন্যবাদ! আমি কীভাবে সাহায্য করতে পারি?
A.zeit = এখন সময় {zeit}।
A.datum = আজ {datum}।
A.ort = কোন জায়গার আবহাওয়া জানতে চান?
A.nichts = দুঃখিত, “{x}” সম্পর্কে কিছু পাইনি।
A.rueckfall = দুঃখিত, ভাষা মডেল ছাড়া আমি এর উত্তর দিতে পারি না। আমাকে আবহাওয়া, সময়, তারিখ,
  হিসাব বা উইকিপিডিয়া সম্পর্কে জিজ্ঞাসা করুন।
A.krise = আপনি একা নন। যদি নিজের জীবন শেষ করার কথা ভাবেন, এখনই কারও সঙ্গে কথা বলুন:
  আপনার দেশের জরুরি নম্বরে ফোন করুন অথবা https://findahelpline.com এ বিনামূল্যের
  হেল্পলাইন খুঁজুন।

@pt Português | wiki=pt | schrift=latin
zeichen = ã;õ
hallo = olá; oi; bom dia; boa tarde; boa noite; e aí
info = quem é você; quem és tu; o que você pode fazer; o que sabes fazer; ajuda
danke = obrigado; obrigada; muito obrigado; muito obrigada; valeu
tschuess = tchau; adeus; até logo; até mais; até breve
wiegehts = como vai; como está; tudo bem; como você está; como estás
wetter = tempo; previsão do tempo; clima; temperatura; chove; chuva; chover; vai chover
zeit = que horas são; que hora é; as horas
datum = que dia é hoje; qual é a data; a data de hoje; que data é hoje
heute = hoje
morgen = amanhã
wiki = o que é {x}; quem é {x}; quem foi {x}; o que são {x}; fale sobre {x}
stopp = em; no; na; de; do; da; para; o; a; os; as; que; qual; como; está; vai; fazer; faz;
  hoje; amanhã; tempo; me; diga; por; favor; agora; chover; chove; chuva; e;
  estar; estará
krise = me matar; quero morrer; suicídio; tirar minha vida; tirar a minha vida
A.intro = Olá! Eu sou o Aquaticy Standard. Posso dizer o tempo, a hora e a data, fazer contas
  e pesquisar na Wikipédia.
A.danke = De nada!
A.tschuess = Tchau! Até breve.
A.wiegehts = Estou bem, obrigado! Como posso ajudar?
A.zeit = São {zeit}.
A.datum = Hoje é {datum}.
A.ort = Para qual lugar você quer saber o tempo?
A.nichts = Desculpe, não encontrei nada sobre “{x}”.
A.rueckfall = Desculpe, sem um modelo de linguagem não consigo responder a isso. Pergunte-me
  sobre o tempo, a hora, a data, uma conta ou algo da Wikipédia.
A.krise = Você não está sozinho. Se está pensando em tirar a própria vida, fale com alguém
  agora: ligue para o número de emergência do seu país ou encontre uma linha de apoio
  gratuita em https://findahelpline.com.

@ru Русский | wiki=ru | schrift=cyrillic
hallo = привет; здравствуйте; здравствуй; добрый день; доброе утро; добрый вечер; приветствую
info = кто ты; кто вы; что ты умеешь; что ты можешь; что вы умеете; помощь; помоги
danke = спасибо; большое спасибо; благодарю; спасибочки
tschuess = пока; до свидания; до встречи; спокойной ночи; всего доброго
wiegehts = как дела; как ты; как поживаешь; как у тебя дела; как вы
wetter = погода; какая погода; погоду; погоды; прогноз погоды; температура; дождь
zeit = который час; сколько времени; сколько сейчас времени; время
datum = какое сегодня число; какое число; какая дата; сегодняшняя дата; какой сегодня день
heute = сегодня
morgen = завтра
wiki = что такое {x}; кто такой {x}; кто такая {x}; кто такие {x}; кто был {x};
  расскажи о {x}; расскажи про {x}
stopp = в; во; на; для; какая; какой; какое; как; будет; сегодня; завтра; сейчас; скажи;
  пожалуйста; там; погода; ли; дождь
krise = покончить с собой; хочу умереть; убить себя; суицид; самоубийство
A.intro = Привет! Я Aquaticy Standard. Я могу сказать погоду, время и дату, посчитать и найти
  информацию в Википедии.
A.danke = Пожалуйста!
A.tschuess = До свидания! До встречи.
A.wiegehts = У меня всё хорошо, спасибо! Чем могу помочь?
A.zeit = Сейчас {zeit}.
A.datum = Сегодня {datum}.
A.ort = Для какого места показать погоду?
A.nichts = Извините, я ничего не нашёл о «{x}».
A.rueckfall = Извините, без языковой модели я не могу на это ответить. Спросите меня о погоде,
  времени, дате, расчёте или о чём-нибудь из Википедии.
A.krise = Вы не одни. Если вы думаете о том, чтобы покончить с собой, поговорите с кем-нибудь
  прямо сейчас: позвоните в местную экстренную службу или найдите бесплатную линию помощи на
  https://findahelpline.com.

@ur اردو | wiki=ur | schrift=arabic
zeichen = ے;ڑ;ٹ;ں;ھ
hallo = السلام علیکم; ہیلو; آداب; صبح بخیر; شام بخیر
info = آپ کون ہیں; تم کون ہو; آپ کیا کر سکتے ہیں; تم کیا کر سکتے ہو; مدد
danke = شکریہ; بہت شکریہ; مہربانی
tschuess = خدا حافظ; اللہ حافظ; پھر ملیں گے; شب بخیر
wiegehts = آپ کیسے ہیں; کیا حال ہے; تم کیسے ہو; کیسے ہو
wetter = موسم; درجہ حرارت; بارش; موسم کا حال
zeit = کیا وقت ہوا ہے; کتنے بجے ہیں; وقت کیا ہے; ٹائم کیا ہے
datum = آج کیا تاریخ ہے; آج کی تاریخ; تاریخ کیا ہے; آج کون سا دن ہے
heute = آج
morgen = کل
wiki = {x} کیا ہے; {x} کون ہے; {x} کون تھا; {x} کے بارے میں بتائیں
stopp = میں; کا; کی; کے; کیا; ہے; ہیں; کیسا; کیسی; رہے; گا; ہوگا; آج; کل; بتائیں; بتاؤ;
  ابھی
krise = خودکشی; مرنا چاہتا; مرنا چاہتی; اپنے آپ کو مار
A.intro = السلام علیکم! میں Aquaticy Standard ہوں۔ میں آپ کو موسم، وقت اور تاریخ بتا سکتا ہوں،
  حساب کر سکتا ہوں اور ویکیپیڈیا پر معلومات تلاش کر سکتا ہوں۔
A.danke = خوش آمدید!
A.tschuess = خدا حافظ! پھر ملیں گے۔
A.wiegehts = میں ٹھیک ہوں، شکریہ! میں آپ کی کیا مدد کر سکتا ہوں؟
A.zeit = ابھی {zeit} بجے ہیں۔
A.datum = آج {datum} ہے۔
A.ort = کس جگہ کا موسم دیکھوں؟
A.nichts = معاف کیجیے، “{x}” کے بارے میں کچھ نہیں ملا۔
A.rueckfall = معاف کیجیے، زبان کے ماڈل کے بغیر میں اس کا جواب نہیں دے سکتا۔ مجھ سے موسم، وقت،
  تاریخ، حساب یا ویکیپیڈیا کے بارے میں پوچھیں۔
A.krise = آپ اکیلے نہیں ہیں۔ اگر آپ اپنی جان لینے کا سوچ رہے ہیں تو ابھی کسی سے بات کریں:
  اپنے ملک کے ایمرجنسی نمبر پر کال کریں یا https://findahelpline.com پر مفت ہیلپ لائن تلاش
  کریں۔

@id Bahasa Indonesia | wiki=id | schrift=latin
hallo = halo; hai; selamat pagi; selamat siang; selamat sore; selamat malam; assalamualaikum
info = siapa kamu; siapa anda; apa yang bisa kamu lakukan; kamu bisa apa; bantuan; tolong
danke = terima kasih; makasih; terima kasih banyak; trims
tschuess = sampai jumpa; selamat tinggal; dadah; bye; sampai nanti
wiegehts = apa kabar; bagaimana kabarmu; gimana kabarnya; kabarnya gimana
wetter = cuaca; prakiraan cuaca; suhu; hujan; ramalan cuaca
zeit = jam berapa; jam berapa sekarang; pukul berapa; sekarang jam berapa
datum = tanggal berapa; tanggal berapa hari ini; hari apa; hari apa ini; tanggal hari ini
heute = hari ini
morgen = besok
wiki = apa itu {x}; siapa itu {x}; siapa {x}; ceritakan tentang {x}; apakah {x} itu
stopp = di; ke; untuk; bagaimana; gimana; apa; seperti; akan; hari; ini; besok; sekarang; yang;
  tolong; dong
krise = bunuh diri; ingin mati; mau mati; mengakhiri hidup
A.intro = Halo! Saya Aquaticy Standard. Saya bisa memberi tahu cuaca, waktu, dan tanggal,
  menghitung, dan mencari di Wikipedia.
A.danke = Sama-sama!
A.tschuess = Sampai jumpa!
A.wiegehts = Saya baik, terima kasih! Ada yang bisa saya bantu?
A.zeit = Sekarang pukul {zeit}.
A.datum = Hari ini {datum}.
A.ort = Untuk tempat mana saya cek cuacanya?
A.nichts = Maaf, saya tidak menemukan apa pun tentang “{x}”.
A.rueckfall = Maaf, tanpa model bahasa saya tidak bisa menjawab itu. Tanyakan tentang cuaca,
  waktu, tanggal, hitungan, atau sesuatu dari Wikipedia.
A.krise = Kamu tidak sendirian. Jika kamu berpikir untuk mengakhiri hidup, bicaralah dengan
  seseorang sekarang: hubungi nomor darurat di negaramu atau cari layanan bantuan gratis di
  https://findahelpline.com.

@ja 日本語 | wiki=ja | schrift=kana,han | nospace
hallo = こんにちは; こんばんは; おはよう; おはようございます; やあ; もしもし
info = あなたは誰; 誰ですか; 何ができる; 何ができますか; ヘルプ; 助けて
danke = ありがとう; ありがとうございます; どうもありがとう; サンキュー
tschuess = さようなら; バイバイ; またね; おやすみ; おやすみなさい; じゃあね
wiegehts = お元気ですか; 元気ですか; 元気; 調子はどう; 調子どう
wetter = 天気; 天気予報; 気温; 雨が; 雨は; 雨の予報; 雨です; 雨降
zeit = 何時ですか; 何時; 今何時; 時間
datum = 今日は何日; 何日ですか; 日付; 何曜日; 今日の日付
heute = 今日
morgen = 明日
wiki = {x}とは; {x}とは何ですか; {x}って何; {x}は何ですか; {x}は誰ですか; {x}って誰
stopp = の; は; を; に; で; が; ですか; ですか？; どう; どうですか; 今日; 明日; 教えて; ください;
  今; か; ね; よ
krise = 死にたい; 自殺; 消えたい; 自分を殺
A.intro = こんにちは！私は Aquaticy Standard です。天気、時刻、日付をお伝えしたり、計算をしたり、
  ウィキペディアで調べたりできます。
A.danke = どういたしまして！
A.tschuess = さようなら！またね。
A.wiegehts = 元気です、ありがとう！何かお手伝いできますか？
A.zeit = 今は {zeit} です。
A.datum = 今日は {datum} です。
A.ort = どの場所の天気を調べますか？
A.nichts = すみません、「{x}」については何も見つかりませんでした。
A.rueckfall = すみません、言語モデルがないとその質問には答えられません。天気、時刻、日付、計算、
  ウィキペディアについて聞いてください。
A.krise = あなたは一人ではありません。命を絶つことを考えているなら、今すぐ誰かに話してください。
  地域の緊急番号に電話するか、https://findahelpline.com で無料の相談窓口を探してください。

@pcm Naijá | wiki=pcm | schrift=latin
hallo = how far; how body; wetin dey; good morning o; hello o
info = who you be; wetin you fit do; wetin you sabi do; help me
danke = tank you; tanks; thank you o; i thank you
tschuess = bye bye; I dey go; make we see later; later o
wiegehts = how you dey; how body dey; you dey alright; how una dey
wetter = weather; how weather be; rain go fall; e go rain
zeit = wetin be the time; what time e be; time don reach
datum = wetin be today date; which day be today; today date
heute = today
morgen = tomorrow
wiki = wetin be {x}; who be {x}; tell me about {x}
stopp = for; dey; how; wetin; be; the; today; tomorrow; for inside; e; go; na; o
krise = I wan kill myself; I wan die; kill myself
A.intro = How far! I be Aquaticy Standard. I fit tell you weather, time and date, do calculation
  and find tins for Wikipedia.
A.danke = No wahala!
A.tschuess = Bye bye! We go see later.
A.wiegehts = I dey kampe, thank you! Wetin I fit do for you?
A.zeit = Time na {zeit}.
A.datum = Today na {datum}.
A.ort = Which place you wan make I check weather for?
A.nichts = Sorry, I no see anything about “{x}”.
A.rueckfall = Sorry, without language model I no fit answer dat one. Ask me about weather, time,
  date, calculation or something for Wikipedia.
A.krise = You no dey alone. If you dey think to end your life, abeg talk to person now: call
  emergency number for your country or find free helpline for https://findahelpline.com.

@mr मराठी | wiki=mr | schrift=devanagari
hallo = नमस्कार; हॅलो; सुप्रभात; शुभ संध्याकाळ
info = तू कोण आहेस; तुम्ही कोण आहात; तू काय करू शकतोस; तुम्ही काय करू शकता; मदत
danke = धन्यवाद; आभारी आहे; खूप धन्यवाद
tschuess = निरोप; पुन्हा भेटू; शुभ रात्री; बाय
wiegehts = कसा आहेस; कशी आहेस; कसे आहात; काय म्हणतोस
wetter = हवामान; तापमान; पाऊस
zeit = किती वाजले; किती वाजले आहेत; वेळ काय आहे
datum = आज कोणती तारीख आहे; आजची तारीख; आज कोणता वार आहे
heute = आज
morgen = उद्या
wiki = {x} म्हणजे काय; {x} काय आहे; {x} कोण आहे; {x} कोण होते
stopp = मध्ये; चे; ची; चा; कसे; कसा; आहे; असेल; आज; उद्या; सांगा; सांग
krise = आत्महत्या; मरायचे आहे; स्वतःला मारून
A.intro = नमस्कार! मी Aquaticy Standard आहे. मी तुम्हाला हवामान, वेळ आणि तारीख सांगू शकतो,
  हिशोब करू शकतो आणि विकिपीडियावर माहिती शोधू शकतो.
A.danke = आपले स्वागत आहे!
A.tschuess = पुन्हा भेटू!
A.wiegehts = मी छान आहे, धन्यवाद! मी तुमची काय मदत करू?
A.zeit = आता {zeit} वाजले आहेत.
A.datum = आज {datum} आहे.
A.ort = कोणत्या ठिकाणचे हवामान पाहू?
A.nichts = माफ करा, “{x}” बद्दल काही सापडले नाही.
A.rueckfall = माफ करा, भाषा मॉडेलशिवाय मी याचे उत्तर देऊ शकत नाही. मला हवामान, वेळ, तारीख,
  हिशोब किंवा विकिपीडियाबद्दल विचारा.
A.krise = तुम्ही एकटे नाही. स्वतःचा जीव घेण्याचा विचार येत असेल तर आत्ताच कोणाशी तरी बोला:
  तुमच्या देशाच्या आपत्कालीन क्रमांकावर फोन करा किंवा https://findahelpline.com वर मोफत
  हेल्पलाइन शोधा.

@te తెలుగు | wiki=te | schrift=telugu
hallo = నమస్కారం; హలో; శుభోదయం; నమస్తే
info = నువ్వు ఎవరు; మీరు ఎవరు; నువ్వు ఏమి చేయగలవు; మీరు ఏమి చేయగలరు; సహాయం
danke = ధన్యవాదాలు; థాంక్స్; చాలా ధన్యవాదాలు
tschuess = వెళ్ళొస్తాను; మళ్ళీ కలుద్దాం; శుభ రాత్రి; బై
wiegehts = ఎలా ఉన్నారు; ఎలా ఉన్నావు; బాగున్నారా
wetter = వాతావరణం; ఉష్ణోగ్రత; వర్షం
zeit = సమయం ఎంత; టైం ఎంత; ఇప్పుడు సమయం ఎంత
datum = ఈరోజు తేదీ ఏమిటి; ఈరోజు తేదీ; తేదీ; ఈరోజు ఏ రోజు
heute = ఈరోజు
morgen = రేపు
wiki = {x} అంటే ఏమిటి; {x} ఎవరు; {x} గురించి చెప్పు
stopp = లో; యొక్క; ఎలా; ఉంది; ఉంటుంది; ఈరోజు; రేపు; చెప్పు; చెప్పండి
krise = ఆత్మహత్య; చనిపోవాలని ఉంది; నన్ను నేను చంపుకో
A.intro = నమస్కారం! నేను Aquaticy Standard. నేను మీకు వాతావరణం, సమయం, తేదీ చెప్పగలను,
  లెక్కలు చేయగలను, వికీపీడియాలో వెతకగలను.
A.danke = మీకు స్వాగతం!
A.tschuess = మళ్ళీ కలుద్దాం!
A.wiegehts = నేను బాగున్నాను, ధన్యవాదాలు! మీకు ఎలా సహాయం చేయగలను?
A.zeit = ఇప్పుడు సమయం {zeit}.
A.datum = ఈరోజు {datum}.
A.ort = ఏ ప్రదేశం వాతావరణం చూడాలి?
A.nichts = క్షమించండి, “{x}” గురించి ఏమీ దొరకలేదు.
A.rueckfall = క్షమించండి, భాషా మోడల్ లేకుండా నేను దీనికి సమాధానం చెప్పలేను. వాతావరణం, సమయం,
  తేదీ, లెక్క లేదా వికీపీడియా గురించి అడగండి.
A.krise = మీరు ఒంటరి కాదు. మీ ప్రాణం తీసుకోవాలని ఆలోచిస్తుంటే, ఇప్పుడే ఎవరితోనైనా మాట్లాడండి:
  మీ దేశ అత్యవసర నంబర్\u200cకు కాల్ చేయండి లేదా https://findahelpline.com లో ఉచిత హెల్ప్\u200cలైన్
  వెతకండి.

@tr Türkçe | wiki=tr | schrift=latin
zeichen = ı;ğ
hallo = merhaba; selam; günaydın; iyi akşamlar; selamün aleyküm; iyi günler
info = sen kimsin; siz kimsiniz; ne yapabilirsin; neler yapabilirsin; yardım
danke = teşekkürler; teşekkür ederim; sağ ol; sağol; çok teşekkürler; mersi
tschuess = hoşça kal; güle güle; görüşürüz; iyi geceler; bay bay
wiegehts = nasılsın; nasılsınız; naber; ne haber; iyi misin
wetter = hava durumu; hava nasıl; havası; hava; sıcaklık; yağmur
zeit = saat kaç; saat kaçta; şu an saat kaç
datum = bugün ayın kaçı; bugün tarih ne; tarih ne; bugün günlerden ne; bugünün tarihi
heute = bugün
morgen = yarın
wiki = {x} nedir; {x} kimdir; {x} ne demek; {x} hakkında bilgi ver
stopp = nasıl; ne; bugün; yarın; için; de; da; olacak; olur; durumu; bana; söyle; şimdi; mi;
  yağacak; mı; yağmur
krise = intihar; ölmek istiyorum; kendimi öldür; canıma kıy
endungen = 'da; 'de; 'ta; 'te; 'nın; 'nin; da; de
A.intro = Merhaba! Ben Aquaticy Standard. Sana hava durumunu, saati ve tarihi söyleyebilir,
  hesap yapabilir ve Vikipedi'de arama yapabilirim.
A.danke = Rica ederim!
A.tschuess = Hoşça kal! Görüşürüz.
A.wiegehts = İyiyim, teşekkürler! Sana nasıl yardım edebilirim?
A.zeit = Saat {zeit}.
A.datum = Bugün {datum}.
A.ort = Hangi yerin hava durumuna bakayım?
A.nichts = Üzgünüm, “{x}” hakkında bir şey bulamadım.
A.rueckfall = Üzgünüm, dil modeli olmadan buna cevap veremem. Bana hava durumunu, saati, tarihi,
  bir hesabı ya da Vikipedi'den bir şey sor.
A.krise = Yalnız değilsin. Hayatına son vermeyi düşünüyorsan lütfen hemen biriyle konuş:
  ülkendeki acil durum numarasını ara ya da https://findahelpline.com adresinde ücretsiz bir
  yardım hattı bul.

@ta தமிழ் | wiki=ta | schrift=tamil
hallo = வணக்கம்; ஹலோ; காலை வணக்கம்; மாலை வணக்கம்
info = நீ யார்; நீங்கள் யார்; நீ என்ன செய்ய முடியும்; உங்களால் என்ன செய்ய முடியும்; உதவி
danke = நன்றி; மிக்க நன்றி; ரொம்ப நன்றி
tschuess = போய் வருகிறேன்; மீண்டும் சந்திப்போம்; இனிய இரவு; பை
wiegehts = எப்படி இருக்கிறீர்கள்; எப்படி இருக்கீங்க; நலமா; எப்படி இருக்கிறாய்
wetter = வானிலை; வெப்பநிலை; மழை
zeit = மணி என்ன; இப்போது மணி என்ன; நேரம் என்ன
datum = இன்று என்ன தேதி; இன்றைய தேதி; தேதி; இன்று என்ன கிழமை
heute = இன்று
morgen = நாளை
wiki = {x} என்றால் என்ன; {x} என்பது என்ன; {x} யார்; {x} பற்றி சொல்
stopp = இல்; இன்; எப்படி; உள்ளது; இருக்கும்; இன்று; நாளை; சொல்லுங்கள்; சொல்; வானிலை
krise = தற்கொலை; சாக வேண்டும்; என்னை கொன்று
A.intro = வணக்கம்! நான் Aquaticy Standard. உங்களுக்கு வானிலை, நேரம், தேதி சொல்லலாம்,
  கணக்கு போடலாம், விக்கிப்பீடியாவில் தேடலாம்.
A.danke = பரவாயில்லை!
A.tschuess = மீண்டும் சந்திப்போம்!
A.wiegehts = நான் நலமாக இருக்கிறேன், நன்றி! நான் எப்படி உதவலாம்?
A.zeit = இப்போது மணி {zeit}.
A.datum = இன்று {datum}.
A.ort = எந்த இடத்தின் வானிலையை பார்க்கட்டும்?
A.nichts = மன்னிக்கவும், “{x}” பற்றி எதுவும் கிடைக்கவில்லை.
A.rueckfall = மன்னிக்கவும், மொழி மாதிரி இல்லாமல் இதற்கு பதில் சொல்ல முடியாது. வானிலை, நேரம்,
  தேதி, கணக்கு அல்லது விக்கிப்பீடியா பற்றி கேளுங்கள்.
A.krise = நீங்கள் தனியாக இல்லை. உங்கள் உயிரை மாய்த்துக்கொள்ள நினைத்தால், இப்போதே யாரிடமாவது
  பேசுங்கள்: உங்கள் நாட்டின் அவசர எண்ணை அழையுங்கள் அல்லது https://findahelpline.com இல்
  இலவச உதவி எண்ணைத் தேடுங்கள்.

@yue 粵語 | wiki=zh-yue | schrift=han | nospace
hallo = 你好; 哈囉; 早晨; 喂
info = 你係邊個; 你識做乜; 你可以做乜嘢; 幫手
danke = 唔該; 多謝; 唔該晒; 多謝晒
tschuess = 拜拜; 再見; 遲啲見; 早唞
wiegehts = 你好嗎; 你點呀; 近排點; 你幾好嗎
wetter = 天氣; 天氣點; 落雨; 氣溫
zeit = 而家幾點; 幾點鐘; 幾點
datum = 今日幾號; 今日係幾號; 今日星期幾
heute = 今日
morgen = 聽日
wiki = {x}係乜嘢; 乜嘢係{x}; {x}係邊個; {x}係咩
stopp = 嘅; 點樣; 點; 呀; 啊; 今日; 聽日; 而家; 喺; 會; 唔; 嗎
krise = 想死; 自殺; 唔想生存
A.intro = 你好！我係 Aquaticy Standard。我可以話你知天氣、時間同日期，幫你計數，
  仲可以喺維基百科搵資料。
A.danke = 唔使客氣！
A.tschuess = 拜拜！遲啲見。
A.wiegehts = 我幾好，多謝！有乜可以幫到你？
A.zeit = 而家係 {zeit}。
A.datum = 今日係 {datum}。
A.ort = 你想查邊度嘅天氣？
A.nichts = 唔好意思，我搵唔到關於「{x}」嘅資料。
A.rueckfall = 唔好意思，冇語言模型我答唔到呢條問題。你可以問我天氣、時間、日期、計數或者維基百科。
A.krise = 你唔係一個人。如果你諗緊結束自己嘅生命，請即刻同人傾吓：打你當地嘅緊急電話，
  或者喺 https://findahelpline.com 搵免費嘅求助熱線。

@vi Tiếng Việt | wiki=vi | schrift=latin
zeichen = ơ;ư;đ;ạ;ả;ế;ệ;ộ;ờ;ữ;ố;ầ
hallo = xin chào; chào bạn; chào; chào buổi sáng; chào buổi tối
info = bạn là ai; bạn có thể làm gì; bạn làm được gì; giúp tôi; trợ giúp
danke = cảm ơn; cám ơn; cảm ơn bạn; cảm ơn nhiều
tschuess = tạm biệt; hẹn gặp lại; chúc ngủ ngon; bai bai
wiegehts = bạn khỏe không; bạn có khỏe không; dạo này thế nào; khỏe không
wetter = thời tiết; nhiệt độ; trời mưa; dự báo thời tiết
zeit = mấy giờ rồi; bây giờ là mấy giờ; mấy giờ
datum = hôm nay ngày mấy; hôm nay là ngày bao nhiêu; ngày hôm nay; hôm nay thứ mấy
heute = hôm nay
morgen = ngày mai
wiki = {x} là gì; {x} là ai; cho tôi biết về {x}
stopp = ở; tại; của; như thế nào; thế nào; ra sao; là; sẽ; hôm nay; ngày mai; bây giờ; cho; tôi;
  biết
krise = tự tử; muốn chết; tự sát; kết thúc cuộc đời
A.intro = Xin chào! Tôi là Aquaticy Standard. Tôi có thể cho bạn biết thời tiết, giờ và ngày,
  làm phép tính và tra cứu Wikipedia.
A.danke = Không có gì!
A.tschuess = Tạm biệt! Hẹn gặp lại.
A.wiegehts = Tôi khỏe, cảm ơn bạn! Tôi có thể giúp gì cho bạn?
A.zeit = Bây giờ là {zeit}.
A.datum = Hôm nay là {datum}.
A.ort = Bạn muốn xem thời tiết ở đâu?
A.nichts = Xin lỗi, tôi không tìm thấy gì về “{x}”.
A.rueckfall = Xin lỗi, không có mô hình ngôn ngữ tôi không thể trả lời câu đó. Hãy hỏi tôi về
  thời tiết, giờ, ngày, phép tính hoặc điều gì đó trên Wikipedia.
A.krise = Bạn không đơn độc. Nếu bạn đang nghĩ đến việc kết thúc cuộc sống, hãy nói chuyện với
  ai đó ngay bây giờ: gọi số khẩn cấp ở nước bạn hoặc tìm đường dây trợ giúp miễn phí tại
  https://findahelpline.com.

@tl Tagalog | wiki=tl | schrift=latin
hallo = kumusta; magandang umaga; magandang hapon; magandang gabi; hello po
info = sino ka; ano ang kaya mong gawin; anong kaya mo; tulong; tulungan mo ako
danke = salamat; maraming salamat; salamat po
tschuess = paalam; ingat; sige; hanggang sa muli; magandang gabi po
wiegehts = kumusta ka; kamusta ka; kumusta ka na; ayos ka lang
wetter = panahon; lagay ng panahon; temperatura; ulan; uulan ba
zeit = anong oras na; ano ang oras; oras na
datum = anong petsa ngayon; petsa ngayon; anong araw ngayon
heute = ngayon
morgen = bukas
wiki = ano ang {x}; sino si {x}; ano ba ang {x}; sabihin mo tungkol sa {x}
stopp = sa; ng; ang; ano; paano; ngayon; bukas; po; ba; ang lagay; kaya
krise = magpakamatay; gusto ko nang mamatay; patayin ang sarili
A.intro = Kumusta! Ako si Aquaticy Standard. Masasabi ko sa iyo ang panahon, oras at petsa,
  makakapagkuwenta ako at makakapaghanap sa Wikipedia.
A.danke = Walang anuman!
A.tschuess = Paalam! Ingat.
A.wiegehts = Mabuti ako, salamat! Paano kita matutulungan?
A.zeit = Ngayon ay {zeit}.
A.datum = Ngayon ay {datum}.
A.ort = Saang lugar ko titingnan ang panahon?
A.nichts = Paumanhin, wala akong nahanap tungkol sa “{x}”.
A.rueckfall = Paumanhin, hindi ko iyan masasagot nang walang language model. Tanungin mo ako
  tungkol sa panahon, oras, petsa, kuwenta o isang bagay sa Wikipedia.
A.krise = Hindi ka nag-iisa. Kung iniisip mong wakasan ang iyong buhay, makipag-usap sa isang tao
  ngayon: tumawag sa emergency number ng iyong bansa o maghanap ng libreng helpline sa
  https://findahelpline.com.

@ko 한국어 | wiki=ko | schrift=hangul | nospace
hallo = 안녕하세요; 안녕; 반갑습니다; 좋은 아침
info = 너는 누구야; 누구세요; 뭘 할 수 있어; 무엇을 할 수 있나요; 도움말; 도와줘
danke = 감사합니다; 고마워; 고맙습니다; 땡큐
tschuess = 안녕히 가세요; 잘가; 잘 가; 또 봐; 잘 자; 안녕히 계세요
wiegehts = 잘 지내; 잘 지내세요; 어떻게 지내; 기분 어때
wetter = 날씨; 기온; 비 와; 일기예보
zeit = 몇 시야; 몇 시예요; 지금 몇 시; 시간
datum = 오늘 며칠; 며칠이야; 날짜; 무슨 요일; 오늘 날짜
heute = 오늘
morgen = 내일
wiki = {x}란 무엇인가요; {x}이 뭐야; {x}가 뭐야; {x}는 뭐야; {x}은 뭐야; {x}는 누구야;
  {x}에 대해 알려줘; {x}이란
stopp = 어때요; 어때; 어떤가요; 오늘; 내일; 지금; 알려줘; 좀
endungen = 에서; 의; 은; 는; 이; 가; 에
krise = 죽고 싶어; 자살; 죽고 싶다
A.intro = 안녕하세요! 저는 Aquaticy Standard입니다. 날씨, 시간, 날짜를 알려 드리고, 계산을 하고,
  위키백과에서 찾아볼 수 있어요.
A.danke = 천만에요!
A.tschuess = 안녕히 가세요! 또 만나요.
A.wiegehts = 잘 지내요, 고마워요! 무엇을 도와드릴까요?
A.zeit = 지금은 {zeit}입니다.
A.datum = 오늘은 {datum}입니다.
A.ort = 어느 곳의 날씨를 볼까요?
A.nichts = 죄송해요, “{x}”에 대해 아무것도 찾지 못했어요.
A.rueckfall = 죄송해요, 언어 모델 없이는 그 질문에 답할 수 없어요. 날씨, 시간, 날짜, 계산이나
  위키백과에 대해 물어보세요.
A.krise = 당신은 혼자가 아닙니다. 삶을 끝내고 싶다는 생각이 든다면 지금 바로 누군가와 이야기하세요:
  지역 긴급 전화번호로 전화하거나 https://findahelpline.com 에서 무료 상담 전화를 찾아보세요.

@fa فارسی | wiki=fa | schrift=arabic
hallo = سلام; درود; صبح بخیر; عصر بخیر; سلام علیکم
info = تو کی هستی; شما کی هستید; چه کاری می\u200cتوانی بکنی; چه کارهایی بلدی; کمک
danke = ممنون; مرسی; متشکرم; سپاس; خیلی ممنون
tschuess = خداحافظ; به امید دیدار; شب بخیر; بای
wiegehts = حالت چطوره; حال شما چطور است; خوبی; چطوری
wetter = هوا; هوای; آب و هوا; وضعیت هوا; دما; باران
zeit = ساعت چنده; ساعت چند است; الان ساعت چند است
datum = امروز چندم است; تاریخ امروز; امروز چه روزی است; تاریخ
heute = امروز
morgen = فردا
wiki = {x} چیست; {x} کیست; {x} چه است; درباره {x} بگو
stopp = در; هوای; برای; چطور; چطوره; است; امروز; فردا; الان; بگو; چه; از
zeichen = پ;چ;ژ;گ
krise = خودکشی; می\u200cخواهم بمیرم; خودم را بکشم
A.intro = سلام! من Aquaticy Standard هستم. می\u200cتوانم وضعیت هوا، ساعت و تاریخ را بگویم، حساب
  کنم و
  در ویکی\u200cپدیا جستجو کنم.
A.danke = خواهش می\u200cکنم!
A.tschuess = خداحافظ! به امید دیدار.
A.wiegehts = خوبم، ممنون! چطور می\u200cتوانم کمکتان کنم؟
A.zeit = الان ساعت {zeit} است.
A.datum = امروز {datum} است.
A.ort = هوای کدام شهر را ببینم؟
A.nichts = متأسفم، درباره «{x}» چیزی پیدا نکردم.
A.rueckfall = متأسفم، بدون مدل زبانی نمی\u200cتوانم به این پاسخ دهم. از من درباره هوا، ساعت، تاریخ،
  حساب یا چیزی از ویکی\u200cپدیا بپرسید.
A.krise = شما تنها نیستید. اگر به پایان دادن به زندگی\u200cتان فکر می\u200cکنید، همین حالا با کسی
  صحبت
  کنید: با شماره اضطراری کشورتان تماس بگیرید یا در https://findahelpline.com یک خط کمک رایگان
  پیدا کنید.

@ha Hausa | wiki=ha | schrift=latin
zeichen = ɓ;ɗ;ƙ
hallo = sannu; sannu da zuwa; ina kwana; barka da safiya; barka da yamma; salamu alaikum
info = wanene kai; me za ka iya yi; mene ne kake iya yi; taimako
danke = na gode; nagode; mun gode; godiya
tschuess = sai anjima; sai an jima; sai wata rana; mu kwana lafiya; sai gobe
wiegehts = yaya kake; yaya kike; ina labari; lafiya kuwa
wetter = yanayi; yanayin yau; zafi; ruwan sama
zeit = karfe nawa; ƙarfe nawa; yanzu karfe nawa
datum = yau kwanan wata nawa; kwanan wata; yau wace rana ce
heute = yau
morgen = gobe
wiki = mene ne {x}; menene {x}; wanene {x}; gaya mini game da {x}
stopp = a; na; ta; yaya; yau; gobe; ne; ce; yanayin; zai; yanzu
krise = kashe kaina; ina so in mutu
A.intro = Sannu! Ni ne Aquaticy Standard. Zan iya gaya maka yanayi, lokaci da kwanan wata, in yi
  lissafi kuma in nemo bayani a Wikipedia.
A.danke = Babu komai!
A.tschuess = Sai anjima!
A.wiegehts = Lafiya lau, na gode! Me zan iya taimaka maka da shi?
A.zeit = Yanzu karfe {zeit}.
A.datum = Yau {datum}.
A.ort = Yanayin wane wuri zan duba?
A.nichts = Yi haƙuri, ban sami komai game da “{x}” ba.
A.rueckfall = Yi haƙuri, ba zan iya amsa wannan ba sai da tsarin harshe. Tambaye ni game da
  yanayi, lokaci, kwanan wata, lissafi ko wani abu daga Wikipedia.
A.krise = Ba kai kaɗai ba ne. Idan kana tunanin kashe kanka, ka yi magana da wani yanzu: kira
  lambar gaggawa ta ƙasarka ko nemi layin taimako kyauta a https://findahelpline.com.

@sw Kiswahili | wiki=sw | schrift=latin
hallo = habari; jambo; hujambo; salamu; habari za asubuhi; habari za jioni; mambo
info = wewe ni nani; unaweza kufanya nini; unajua kufanya nini; msaada; nisaidie
danke = asante; asante sana; nashukuru; ahsante
tschuess = kwaheri; tutaonana; usiku mwema; kwa heri
wiegehts = habari yako; hujambo; u hali gani; habari gani; uko poa
wetter = hali ya hewa; hewa; joto; mvua
zeit = saa ngapi; ni saa ngapi sasa; saa ngapi sasa
datum = leo ni tarehe ngapi; tarehe ya leo; tarehe; leo ni siku gani
heute = leo
morgen = kesho
wiki = nini ni {x}; {x} ni nini; {x} ni nani; niambie kuhusu {x}
stopp = ya; huko; katika; kwa; ikoje; ni; vipi; leo; kesho; hali; sasa; za
krise = kujiua; nataka kufa; kujitoa uhai
A.intro = Habari! Mimi ni Aquaticy Standard. Ninaweza kukuambia hali ya hewa, saa na tarehe,
  kufanya hesabu na kutafuta kwenye Wikipedia.
A.danke = Karibu!
A.tschuess = Kwaheri! Tutaonana.
A.wiegehts = Niko salama, asante! Nikusaidie nini?
A.zeit = Sasa ni saa {zeit}.
A.datum = Leo ni {datum}.
A.ort = Nitazame hali ya hewa ya mahali gani?
A.nichts = Samahani, sikupata chochote kuhusu “{x}”.
A.rueckfall = Samahani, siwezi kujibu hilo bila mfumo wa lugha. Niulize kuhusu hali ya hewa, saa,
  tarehe, hesabu au kitu kutoka Wikipedia.
A.krise = Hauko peke yako. Ikiwa unafikiria kujiua, tafadhali zungumza na mtu sasa hivi: piga
  namba ya dharura ya nchi yako au tafuta msaada wa bure kwenye https://findahelpline.com.

@jv Basa Jawa | wiki=jv | schrift=latin
hallo = sugeng enjing; sugeng siang; sugeng sonten; sugeng dalu; halo; piye kabare
info = sapa kowe; panjenengan sinten; kowe bisa apa; pitulungan
danke = matur nuwun; maturnuwun; suwun; matur suwun
tschuess = sugeng tindak; nganti ketemu maneh; pamit
wiegehts = piye kabare; kepiye kabare; pripun kabaripun; apik-apik wae
wetter = cuaca; hawa; udan; suhu
zeit = jam pira; saiki jam pira; jam pinten
datum = tanggal pira; dina iki tanggal pira; dina apa saiki
heute = dina iki
morgen = sesuk
wiki = apa iku {x}; sapa iku {x}; critakna babagan {x}
stopp = ing; neng; ning; piye; kepiye; dina; iki; sesuk; saiki; ya; cuacane
krise = bunuh diri; pengin mati; kepengin mati
A.intro = Sugeng rawuh! Aku Aquaticy Standard. Aku bisa ngandhani cuaca, jam lan tanggal, ngitung
  lan nggoleki ing Wikipedia.
A.danke = Sami-sami!
A.tschuess = Sugeng tindak! Nganti ketemu maneh.
A.wiegehts = Aku apik, matur nuwun! Ana sing bisa tak bantu?
A.zeit = Saiki jam {zeit}.
A.datum = Dina iki {datum}.
A.ort = Cuaca ing panggonan endi sing arep tak deleng?
A.nichts = Nyuwun pangapunten, aku ora nemokake apa-apa babagan “{x}”.
A.rueckfall = Nyuwun pangapunten, tanpa model basa aku ora bisa mangsuli kuwi. Takon bab cuaca,
  jam, tanggal, etungan utawa samubarang saka Wikipedia.
A.krise = Kowe ora dhewekan. Yen kowe mikir arep mungkasi uripmu, tulung omong karo wong saiki
  uga: telpon nomer darurat ing negaramu utawa golek layanan bantuan gratis ing
  https://findahelpline.com.

@it Italiano | wiki=it | schrift=latin
hallo = ciao; salve; buongiorno; buonasera; buon pomeriggio
info = chi sei; cosa sai fare; cosa puoi fare; aiuto; che cosa sei
danke = grazie; grazie mille; ti ringrazio; molte grazie
tschuess = arrivederci; ci vediamo; a presto; buonanotte; addio
wiegehts = come stai; come va; come sta; tutto bene
wetter = che tempo fa; il tempo; meteo; previsioni; temperatura; piove; pioggia;
  pioverà; che tempo farà
zeit = che ore sono; che ora è; l'ora
datum = che giorno è oggi; che data è; la data di oggi; quanti ne abbiamo
heute = oggi
morgen = domani
wiki = cos'è {x}; cosa è {x}; che cos'è {x}; chi è {x}; chi era {x}; parlami di {x}
stopp = a; in; di; il; la; lo; per; che; fa; farà; com'è; oggi; domani; tempo; sarà; dimmi;
  ora; adesso; pioverà; piove; pioggia; e
krise = suicidarmi; voglio morire; uccidermi; togliermi la vita; suicidio
A.intro = Ciao! Sono Aquaticy Standard. Posso dirti il meteo, l'ora e la data, fare calcoli e
  cercare su Wikipedia.
A.danke = Prego!
A.tschuess = Arrivederci! A presto.
A.wiegehts = Sto bene, grazie! Come posso aiutarti?
A.zeit = Sono le {zeit}.
A.datum = Oggi è il {datum}.
A.ort = Per quale luogo vuoi il meteo?
A.nichts = Mi dispiace, non ho trovato nulla su “{x}”.
A.rueckfall = Mi dispiace, senza un modello linguistico non posso rispondere. Chiedimi il meteo,
  l'ora, la data, un calcolo o qualcosa su Wikipedia.
A.krise = Non sei solo. Se stai pensando di toglierti la vita, parla con qualcuno adesso: chiama
  il numero di emergenza del tuo paese o trova una linea di ascolto gratuita su
  https://findahelpline.com.

@pa ਪੰਜਾਬੀ | wiki=pa | schrift=gurmukhi
hallo = ਸਤ ਸ੍ਰੀ ਅਕਾਲ; ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ; ਹੈਲੋ; ਨਮਸਤੇ
info = ਤੁਸੀਂ ਕੌਣ ਹੋ; ਤੂੰ ਕੌਣ ਹੈਂ; ਤੁਸੀਂ ਕੀ ਕਰ ਸਕਦੇ ਹੋ; ਮਦਦ
danke = ਧੰਨਵਾਦ; ਸ਼ੁਕਰੀਆ; ਬਹੁਤ ਧੰਨਵਾਦ
tschuess = ਅਲਵਿਦਾ; ਫਿਰ ਮਿਲਾਂਗੇ; ਸ਼ੁਭ ਰਾਤ; ਬਾਏ
wiegehts = ਤੁਸੀਂ ਕਿਵੇਂ ਹੋ; ਕੀ ਹਾਲ ਹੈ; ਕਿਵੇਂ ਹੋ
wetter = ਮੌਸਮ; ਤਾਪਮਾਨ; ਮੀਂਹ
zeit = ਕਿੰਨੇ ਵਜੇ ਹਨ; ਟਾਈਮ ਕੀ ਹੈ; ਸਮਾਂ ਕੀ ਹੈ
datum = ਅੱਜ ਕਿਹੜੀ ਤਾਰੀਖ ਹੈ; ਅੱਜ ਦੀ ਤਾਰੀਖ; ਅੱਜ ਕਿਹੜਾ ਦਿਨ ਹੈ
heute = ਅੱਜ
morgen = ਕੱਲ੍ਹ
wiki = {x} ਕੀ ਹੈ; {x} ਕੌਣ ਹੈ; {x} ਬਾਰੇ ਦੱਸੋ
stopp = ਵਿੱਚ; ਦਾ; ਦੀ; ਦੇ; ਕਿਵੇਂ; ਕੀ; ਹੈ; ਰਹੇਗਾ; ਅੱਜ; ਕੱਲ੍ਹ; ਦੱਸੋ
krise = ਖੁਦਕੁਸ਼ੀ; ਮਰਨਾ ਚਾਹੁੰਦਾ; ਮਰਨਾ ਚਾਹੁੰਦੀ
A.intro = ਸਤ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ Aquaticy Standard ਹਾਂ। ਮੈਂ ਤੁਹਾਨੂੰ ਮੌਸਮ, ਸਮਾਂ ਅਤੇ ਤਾਰੀਖ ਦੱਸ ਸਕਦਾ ਹਾਂ,
  ਹਿਸਾਬ ਲਗਾ ਸਕਦਾ ਹਾਂ ਅਤੇ ਵਿਕੀਪੀਡੀਆ ਉੱਤੇ ਖੋਜ ਸਕਦਾ ਹਾਂ।
A.danke = ਜੀ ਆਇਆਂ ਨੂੰ!
A.tschuess = ਅਲਵਿਦਾ! ਫਿਰ ਮਿਲਾਂਗੇ।
A.wiegehts = ਮੈਂ ਠੀਕ ਹਾਂ, ਧੰਨਵਾਦ! ਮੈਂ ਤੁਹਾਡੀ ਕੀ ਮਦਦ ਕਰਾਂ?
A.zeit = ਹੁਣ {zeit} ਵਜੇ ਹਨ।
A.datum = ਅੱਜ {datum} ਹੈ।
A.ort = ਕਿਸ ਥਾਂ ਦਾ ਮੌਸਮ ਵੇਖਾਂ?
A.nichts = ਮਾਫ਼ ਕਰਨਾ, “{x}” ਬਾਰੇ ਕੁਝ ਨਹੀਂ ਮਿਲਿਆ।
A.rueckfall = ਮਾਫ਼ ਕਰਨਾ, ਭਾਸ਼ਾ ਮਾਡਲ ਤੋਂ ਬਿਨਾਂ ਮੈਂ ਇਸ ਦਾ ਜਵਾਬ ਨਹੀਂ ਦੇ ਸਕਦਾ। ਮੈਨੂੰ ਮੌਸਮ, ਸਮਾਂ,
  ਤਾਰੀਖ, ਹਿਸਾਬ ਜਾਂ ਵਿਕੀਪੀਡੀਆ ਬਾਰੇ ਪੁੱਛੋ।
A.krise = ਤੁਸੀਂ ਇਕੱਲੇ ਨਹੀਂ ਹੋ। ਜੇ ਤੁਸੀਂ ਆਪਣੀ ਜਾਨ ਲੈਣ ਬਾਰੇ ਸੋਚ ਰਹੇ ਹੋ, ਤਾਂ ਹੁਣੇ ਕਿਸੇ ਨਾਲ ਗੱਲ ਕਰੋ:
  ਆਪਣੇ ਦੇਸ਼ ਦੇ ਐਮਰਜੈਂਸੀ ਨੰਬਰ ਉੱਤੇ ਫ਼ੋਨ ਕਰੋ ਜਾਂ https://findahelpline.com ਉੱਤੇ ਮੁਫ਼ਤ
  ਹੈਲਪਲਾਈਨ ਲੱਭੋ।

@gu ગુજરાતી | wiki=gu | schrift=gujarati
hallo = નમસ્તે; કેમ છો; હેલો; સુપ્રભાત; જય શ્રી કૃષ્ણ
info = તમે કોણ છો; તું કોણ છે; તમે શું કરી શકો; મદદ
danke = આભાર; ધન્યવાદ; ખૂબ આભાર
tschuess = આવજો; ફરી મળીશું; શુભ રાત્રિ; બાય
wiegehts = તમે કેમ છો; કેમ છો; શું ચાલે છે; મજામાં
wetter = હવામાન; તાપમાન; વરસાદ
zeit = કેટલા વાગ્યા; કેટલા વાગ્યા છે; સમય શું છે
datum = આજે કઈ તારીખ છે; આજની તારીખ; આજે કયો વાર છે
heute = આજે
morgen = કાલે
wiki = {x} શું છે; {x} કોણ છે; {x} વિશે કહો
stopp = માં; નું; ની; નો; ના; કેવું; શું; છે; રહેશે; આજે; કાલે; કહો
krise = આત્મહત્યા; મરી જવું છે; મરવું છે
A.intro = નમસ્તે! હું Aquaticy Standard છું. હું તમને હવામાન, સમય અને તારીખ કહી શકું છું,
  ગણતરી કરી શકું છું અને વિકિપીડિયા પર શોધી શકું છું.
A.danke = આપનું સ્વાગત છે!
A.tschuess = આવજો! ફરી મળીશું.
A.wiegehts = હું મજામાં છું, આભાર! હું તમારી શું મદદ કરું?
A.zeit = અત્યારે {zeit} વાગ્યા છે.
A.datum = આજે {datum} છે.
A.ort = કયા સ્થળનું હવામાન જોઉં?
A.nichts = માફ કરશો, “{x}” વિશે કંઈ મળ્યું નહીં.
A.rueckfall = માફ કરશો, ભાષા મોડેલ વિના હું આનો જવાબ આપી શકતો નથી. મને હવામાન, સમય, તારીખ,
  ગણતરી અથવા વિકિપીડિયા વિશે પૂછો.
A.krise = તમે એકલા નથી. જો તમે તમારો જીવ લેવાનું વિચારી રહ્યા હો, તો હમણાં જ કોઈની સાથે વાત
  કરો: તમારા દેશના ઇમરજન્સી નંબર પર ફોન કરો અથવા https://findahelpline.com પર મફત હેલ્પલાઇન
  શોધો.

@th ไทย | wiki=th | schrift=thai | nospace
hallo = สวัสดี; สวัสดีครับ; สวัสดีค่ะ; หวัดดี
info = คุณเป็นใคร; คุณคือใคร; คุณทำอะไรได้บ้าง; ช่วยด้วย; ช่วยเหลือ
danke = ขอบคุณ; ขอบคุณครับ; ขอบคุณค่ะ; ขอบใจ; ขอบคุณมาก
tschuess = ลาก่อน; บ๊ายบาย; แล้วพบกันใหม่; ราตรีสวัสดิ์
wiegehts = สบายดีไหม; สบายดีมั้ย; เป็นอย่างไรบ้าง; เป็นไงบ้าง
wetter = สภาพอากาศ; อากาศ; อุณหภูมิ; ฝนตก
zeit = กี่โมงแล้ว; ตอนนี้กี่โมง; กี่โมง; เวลา
datum = วันนี้วันที่เท่าไหร่; วันที่เท่าไหร่; วันนี้วันอะไร; วันที่
heute = วันนี้
morgen = พรุ่งนี้
wiki = {x}คืออะไร; {x}คือใคร; อะไรคือ{x}; บอกเกี่ยวกับ{x}
stopp = ที่; ของ; ใน; เป็นอย่างไร; เป็นยังไง; ยังไง; ไหม; มั้ย; วันนี้; พรุ่งนี้; ตอนนี้; ครับ; ค่ะ;
  จะ; บ้าง
krise = ฆ่าตัวตาย; อยากตาย; ไม่อยากมีชีวิตอยู่
A.intro = สวัสดี! ฉันคือ Aquaticy Standard ฉันบอกสภาพอากาศ เวลา และวันที่ได้ คำนวณได้
  และค้นหาในวิกิพีเดียได้
A.danke = ยินดีครับ!
A.tschuess = ลาก่อน! แล้วพบกันใหม่
A.wiegehts = สบายดี ขอบคุณ! มีอะไรให้ช่วยไหม?
A.zeit = ตอนนี้เวลา {zeit}
A.datum = วันนี้คือ {datum}
A.ort = อยากรู้สภาพอากาศที่ไหน?
A.nichts = ขออภัย ไม่พบข้อมูลเกี่ยวกับ “{x}”
A.rueckfall = ขออภัย หากไม่มีโมเดลภาษา ฉันตอบคำถามนี้ไม่ได้ ลองถามเรื่องสภาพอากาศ เวลา วันที่
  การคำนวณ หรือเรื่องในวิกิพีเดีย
A.krise = คุณไม่ได้อยู่คนเดียว หากคุณกำลังคิดจะจบชีวิตตัวเอง โปรดคุยกับใครสักคนตอนนี้:
  โทรหาหมายเลขฉุกเฉินในประเทศของคุณ หรือหาสายด่วนช่วยเหลือฟรีที่ https://findahelpline.com

@kn ಕನ್ನಡ | wiki=kn | schrift=kannada
hallo = ನಮಸ್ಕಾರ; ಹಲೋ; ಶುಭೋದಯ; ನಮಸ್ತೆ
info = ನೀನು ಯಾರು; ನೀವು ಯಾರು; ನೀನು ಏನು ಮಾಡಬಲ್ಲೆ; ನೀವು ಏನು ಮಾಡಬಲ್ಲಿರಿ; ಸಹಾಯ
danke = ಧನ್ಯವಾದ; ಧನ್ಯವಾದಗಳು; ಥ್ಯಾಂಕ್ಸ್
tschuess = ಹೋಗಿ ಬರುತ್ತೇನೆ; ಮತ್ತೆ ಸಿಗೋಣ; ಶುಭ ರಾತ್ರಿ; ಬೈ
wiegehts = ಹೇಗಿದ್ದೀರಿ; ಹೇಗಿದ್ದೀಯ; ಚೆನ್ನಾಗಿದ್ದೀರಾ
wetter = ಹವಾಮಾನ; ತಾಪಮಾನ; ಮಳೆ
zeit = ಸಮಯ ಎಷ್ಟು; ಗಂಟೆ ಎಷ್ಟು; ಈಗ ಎಷ್ಟು ಗಂಟೆ
datum = ಇಂದು ಯಾವ ದಿನಾಂಕ; ಇಂದಿನ ದಿನಾಂಕ; ಇಂದು ಯಾವ ವಾರ
heute = ಇಂದು
morgen = ನಾಳೆ
wiki = {x} ಎಂದರೇನು; {x} ಎಂದರೆ ಏನು; {x} ಯಾರು; {x} ಬಗ್ಗೆ ಹೇಳು
stopp = ರಲ್ಲಿ; ಅಲ್ಲಿ; ಹೇಗಿದೆ; ಏನು; ಇದೆ; ಇರುತ್ತದೆ; ಇಂದು; ನಾಳೆ; ಹೇಳಿ; ಹೇಳು
krise = ಆತ್ಮಹತ್ಯೆ; ಸಾಯಬೇಕು; ಸಾಯಲು ಬಯಸುತ್ತೇನೆ
A.intro = ನಮಸ್ಕಾರ! ನಾನು Aquaticy Standard. ನಾನು ನಿಮಗೆ ಹವಾಮಾನ, ಸಮಯ ಮತ್ತು ದಿನಾಂಕ ಹೇಳಬಲ್ಲೆ,
  ಲೆಕ್ಕ ಮಾಡಬಲ್ಲೆ ಮತ್ತು ವಿಕಿಪೀಡಿಯಾದಲ್ಲಿ ಹುಡುಕಬಲ್ಲೆ.
A.danke = ಸ್ವಾಗತ!
A.tschuess = ಮತ್ತೆ ಸಿಗೋಣ!
A.wiegehts = ನಾನು ಚೆನ್ನಾಗಿದ್ದೇನೆ, ಧನ್ಯವಾದ! ನಾನು ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?
A.zeit = ಈಗ ಸಮಯ {zeit}.
A.datum = ಇಂದು {datum}.
A.ort = ಯಾವ ಸ್ಥಳದ ಹವಾಮಾನ ನೋಡಲಿ?
A.nichts = ಕ್ಷಮಿಸಿ, “{x}” ಬಗ್ಗೆ ಏನೂ ಸಿಗಲಿಲ್ಲ.
A.rueckfall = ಕ್ಷಮಿಸಿ, ಭಾಷಾ ಮಾದರಿ ಇಲ್ಲದೆ ನಾನು ಇದಕ್ಕೆ ಉತ್ತರಿಸಲಾರೆ. ಹವಾಮಾನ, ಸಮಯ, ದಿನಾಂಕ, ಲೆಕ್ಕ
  ಅಥವಾ ವಿಕಿಪೀಡಿಯಾ ಬಗ್ಗೆ ಕೇಳಿ.
A.krise = ನೀವು ಒಂಟಿಯಲ್ಲ. ನಿಮ್ಮ ಜೀವ ತೆಗೆದುಕೊಳ್ಳುವ ಯೋಚನೆ ಬರುತ್ತಿದ್ದರೆ, ಈಗಲೇ ಯಾರ ಜೊತೆಗಾದರೂ
  ಮಾತನಾಡಿ: ನಿಮ್ಮ ದೇಶದ ತುರ್ತು ಸಂಖ್ಯೆಗೆ ಕರೆ ಮಾಡಿ ಅಥವಾ https://findahelpline.com ನಲ್ಲಿ
  ಉಚಿತ ಸಹಾಯವಾಣಿ ಹುಡುಕಿ.

@am አማርኛ | wiki=am | schrift=ethiopic
hallo = ሰላም; ጤና ይስጥልኝ; እንደምን አደርክ; እንደምን አደርሽ; ሰላም ነው
info = ማን ነህ; ማን ነሽ; ምን ማድረግ ትችላለህ; እርዳታ
danke = አመሰግናለሁ; በጣም አመሰግናለሁ; እግዚአብሔር ይስጥልኝ
tschuess = ደህና ሁን; ደህና ሁኚ; ቻው; በኋላ እንገናኝ; ደህና እደር
wiegehts = እንዴት ነህ; እንዴት ነሽ; እንዴት ነዎት; ደህና ነህ
wetter = የአየር ሁኔታ; አየር ሁኔታ; ሙቀት; ዝናብ
zeit = ስንት ሰዓት ነው; ሰዓቱ ስንት ነው; አሁን ስንት ሰዓት ነው
datum = ዛሬ ስንት ነው; የዛሬ ቀን; ዛሬ ምን ቀን ነው
heute = ዛሬ
morgen = ነገ
wiki = {x} ምንድን ነው; {x} ምንድነው; {x} ማን ነው; ስለ {x} ንገረኝ
stopp = በ; የ; ውስጥ; እንዴት; ነው; ይሆናል; ዛሬ; ነገ; አሁን; ንገረኝ
krise = ራሴን ማጥፋት; መሞት እፈልጋለሁ; ራሴን መግደል
A.intro = ሰላም! እኔ Aquaticy Standard ነኝ። የአየር ሁኔታን፣ ሰዓትንና ቀንን ልነግርህ፣ ማስላት እና
  በዊኪፔዲያ መፈለግ እችላለሁ።
A.danke = ምንም አይደለም!
A.tschuess = ደህና ሁን! በኋላ እንገናኝ።
A.wiegehts = ደህና ነኝ፣ አመሰግናለሁ! እንዴት ልርዳህ?
A.zeit = አሁን {zeit} ነው።
A.datum = ዛሬ {datum} ነው።
A.ort = የየትኛውን ቦታ የአየር ሁኔታ ልይ?
A.nichts = ይቅርታ፣ ስለ “{x}” ምንም አላገኘሁም።
A.rueckfall = ይቅርታ፣ ያለ ቋንቋ ሞዴል ይህን መመለስ አልችልም። ስለ አየር ሁኔታ፣ ሰዓት፣ ቀን፣ ሂሳብ ወይም
  ከዊኪፔዲያ የሆነ ነገር ጠይቀኝ።
A.krise = ብቻህን አይደለህም። ሕይወትህን ለማጥፋት እያሰብክ ከሆነ አሁኑኑ ከአንድ ሰው ጋር ተነጋገር:
  የአገርህን የአደጋ ጊዜ ቁጥር ደውል ወይም በ https://findahelpline.com ነፃ የእርዳታ መስመር ፈልግ።

@bho भोजपुरी | wiki=bh | schrift=devanagari
hallo = प्रणाम; राम राम; का हाल बा; नमस्ते जी
info = तू के हउअ; रउआ के हईं; तू का कर सकेल; मदद करीं
danke = धन्यवाद बा; बहुत धन्यवाद बा; शुक्रिया बा
tschuess = फेर मिलल जाई; चलत बानी; राम राम जी
wiegehts = का हाल बा; कइसन बाड़; कइसे बानी; सब ठीक बा
wetter = मौसम कइसन बा; मौसम; बरखा
zeit = केतना बजल बा; टाइम का भइल; समय का बा
datum = आज कवन तारीख बा; आज के तारीख; आज कवन दिन बा
heute = आज
morgen = काल्ह
wiki = {x} का ह; {x} का होला; {x} के ह; {x} के बारे में बताईं
stopp = में; के; कइसन; बा; रही; आज; काल्ह; बताईं; ना
krise = आत्महत्या; मर जाए के मन; मरे के चाहत बानी
A.intro = प्रणाम! हम Aquaticy Standard हईं। हम रउआ के मौसम, समय आ तारीख बता सकीले, हिसाब कर
  सकीले आ विकिपीडिया पर खोज सकीले।
A.danke = कवनो बात ना!
A.tschuess = फेर मिलल जाई!
A.wiegehts = हम ठीक बानी, धन्यवाद! हम रउआ के का मदद करीं?
A.zeit = अभी {zeit} बजल बा।
A.datum = आज {datum} बा।
A.ort = कवना जगह के मौसम देखीं?
A.nichts = माफ करीं, “{x}” के बारे में कुछ ना मिलल।
A.rueckfall = माफ करीं, भाषा मॉडल के बिना हम एकर जवाब ना दे सकीं। हमसे मौसम, समय, तारीख, हिसाब
  भा विकिपीडिया के बारे में पूछीं।
A.krise = रउआ अकेले नइखीं। अगर अपना जान लेवे के बात सोचत बानी, त अबहिंए केहू से बात करीं:
  अपना देश के आपातकालीन नंबर पर फोन करीं भा https://findahelpline.com पर मुफ्त हेल्पलाइन
  खोजीं।

@yo Yorùbá | wiki=yo | schrift=latin
zeichen = ẹ;ọ;ṣ
hallo = bawo ni; ẹ n lẹ; pẹlẹ o; ẹ kaaro; ẹ kaasan; ẹ kaalẹ; e kaaro
info = tani ẹ; tani ọ; kini o le ṣe; iranlọwọ; ran mi lọwọ
danke = ẹ ṣeun; e se; o ṣeun; ẹ ṣeun pupọ; e se gan
tschuess = o dabọ; ó dàbọ̀; ma a ri ọ; o di igba; o daaro
wiegehts = bawo ni o ṣe wa; ṣe daadaa ni; bawo lo wa; ṣe alaafia ni
wetter = oju ọjọ; ojú ọjọ́; ojo; ooru
zeit = aago meloo ni; aago mélòó ni; ago melo
datum = ọjọ wo ni oni; ọjọ melo ni oni; ọjọ oni
heute = oni
morgen = ọla
wiki = kini {x}; tani {x}; sọ fun mi nipa {x}
stopp = ni; ti; ni ilu; bawo; oni; ọla; ṣe; wa; yoo; ri
krise = pa ara mi; mo fẹ ku; para ẹni
A.intro = Bawo ni! Emi ni Aquaticy Standard. Mo le sọ oju ọjọ, aago ati ọjọ fun ọ, ṣe iṣiro ati
  wa nkan lori Wikipedia.
A.danke = Ko si wahala!
A.tschuess = O dabọ! Ma a ri ọ.
A.wiegehts = Mo wa daadaa, ẹ ṣeun! Kini mo le ṣe fun ọ?
A.zeit = Aago {zeit} ni bayi.
A.datum = Oni ni {datum}.
A.ort = Oju ọjọ ibo ni ki n wo?
A.nichts = Ẹ ma binu, mi o ri nkankan nipa “{x}”.
A.rueckfall = Ẹ ma binu, laisi awoṣe ede mi o le dahun iyẹn. Bi mi nipa oju ọjọ, aago, ọjọ,
  iṣiro tabi nkan lati Wikipedia.
A.krise = Iwọ kii ṣe nikan. Ti o ba n ronu lati pa ara rẹ, jọwọ ba ẹnikan sọrọ ni bayi: pe nọmba
  pajawiri orilẹ-ede rẹ tabi wa laini iranlọwọ ọfẹ ni https://findahelpline.com.

@my မြန်မာ | wiki=my | schrift=myanmar | nospace
hallo = မင်္ဂလာပါ; ဟယ်လို; နေကောင်းလား
info = မင်းဘယ်သူလဲ; ခင်ဗျားဘယ်သူလဲ; ဘာလုပ်နိုင်လဲ; အကူအညီ
danke = ကျေးဇူးတင်ပါတယ်; ကျေးဇူးပဲ; ကျေးဇူးအများကြီးတင်ပါတယ်
tschuess = သွားတော့မယ်; နောက်မှတွေ့မယ်; ဘိုင်ဘိုင်; ကောင်းသောညပါ
wiegehts = နေကောင်းလား; ဘယ်လိုနေလဲ; အဆင်ပြေလား
wetter = ရာသီဥတု; မိုးလေဝသ; အပူချိန်; မိုးရွာ
zeit = ဘယ်နှစ်နာရီလဲ; အခုဘယ်အချိန်လဲ; အချိန်
datum = ဒီနေ့ဘယ်ရက်လဲ; ရက်စွဲ; ဒီနေ့ဘာနေ့လဲ
heute = ဒီနေ့
morgen = မနက်ဖြန်
wiki = {x}ဆိုတာဘာလဲ; {x}ဆိုတာ ဘာလဲ; {x}ကဘယ်သူလဲ
stopp = မှာ; ရဲ့; ဘယ်လိုလဲ; ဘယ်လို; လဲ; ဒီနေ့; မနက်ဖြန်; အခု; က
krise = သေချင်တယ်; ကိုယ့်ကိုယ်ကိုသတ်; မိမိကိုယ်ကိုသတ်သေ
A.intro = မင်္ဂလာပါ! ကျွန်တော်က Aquaticy Standard ပါ။ ရာသီဥတု၊ အချိန်နဲ့ ရက်စွဲကို ပြောပြနိုင်ပါတယ်၊
  တွက်ချက်ပေးနိုင်ပြီး ဝီကီပီးဒီးယားမှာ ရှာပေးနိုင်ပါတယ်။
A.danke = ရပါတယ်!
A.tschuess = နောက်မှတွေ့မယ်!
A.wiegehts = နေကောင်းပါတယ်၊ ကျေးဇူးပါ! ဘာကူညီပေးရမလဲ?
A.zeit = အခု {zeit} ဖြစ်ပါတယ်။
A.datum = ဒီနေ့ {datum} ဖြစ်ပါတယ်။
A.ort = ဘယ်နေရာရဲ့ ရာသီဥတုကို ကြည့်ပေးရမလဲ?
A.nichts = တောင်းပန်ပါတယ်၊ “{x}” အကြောင်း ဘာမှမတွေ့ပါ။
A.rueckfall = တောင်းပန်ပါတယ်၊ ဘာသာစကားမော်ဒယ်မပါဘဲ ဒါကို မဖြေနိုင်ပါ။ ရာသီဥတု၊ အချိန်၊ ရက်စွဲ၊
  တွက်ချက်မှု ဒါမှမဟုတ် ဝီကီပီးဒီးယားအကြောင်း မေးပါ။
A.krise = သင်တစ်ယောက်တည်း မဟုတ်ပါ။ ကိုယ့်အသက်ကို အဆုံးသတ်ဖို့ စဉ်းစားနေရင် အခုပဲ တစ်ယောက်ယောက်နဲ့
  စကားပြောပါ: သင့်နိုင်ငံရဲ့ အရေးပေါ်နံပါတ်ကို ဖုန်းဆက်ပါ သို့မဟုတ် https://findahelpline.com
  မှာ အခမဲ့အကူအညီလိုင်းကို ရှာပါ။

@pl Polski | wiki=pl | schrift=latin
zeichen = ł;ń;ś;ź;ż;ą;ę
hallo = cześć; dzień dobry; witaj; witam; dobry wieczór; siema
info = kim jesteś; co potrafisz; co umiesz; co możesz zrobić; pomoc; pomóż
danke = dziękuję; dzięki; dziękuję bardzo; wielkie dzięki
tschuess = do widzenia; na razie; pa; do zobaczenia; dobranoc; cześć na razie
wiegehts = jak się masz; co słychać; jak leci; jak się pan ma; jak się pani ma
wetter = pogoda; pogodę; pogody; prognoza pogody; temperatura; deszcz; pada; padać
zeit = która godzina; która jest godzina; ile jest godzin
datum = jaka jest dzisiaj data; jaki dziś dzień; którego dzisiaj; dzisiejsza data
heute = dzisiaj
morgen = jutro
wiki = co to jest {x}; czym jest {x}; kto to jest {x}; kim jest {x}; kim był {x};
  opowiedz o {x}
stopp = w; we; na; dla; jaka; jaki; jak; będzie; dzisiaj; dziś; jutro; teraz; powiedz; jest;
  czy; padać; pada; deszcz
krise = zabić się; chcę umrzeć; samobójstwo; odebrać sobie życie
A.intro = Cześć! Jestem Aquaticy Standard. Mogę podać pogodę, godzinę i datę, liczyć i szukać
  w Wikipedii.
A.danke = Proszę bardzo!
A.tschuess = Do widzenia! Na razie.
A.wiegehts = Dobrze, dziękuję! W czym mogę pomóc?
A.zeit = Jest {zeit}.
A.datum = Dzisiaj jest {datum}.
A.ort = Dla jakiego miejsca sprawdzić pogodę?
A.nichts = Przepraszam, nic nie znalazłem o „{x}”.
A.rueckfall = Przepraszam, bez modelu językowego nie mogę na to odpowiedzieć. Zapytaj mnie
  o pogodę, godzinę, datę, obliczenie albo coś z Wikipedii.
A.krise = Nie jesteś sam. Jeśli myślisz o odebraniu sobie życia, porozmawiaj z kimś teraz:
  zadzwoń pod numer alarmowy w swoim kraju albo znajdź bezpłatny telefon zaufania na
  https://findahelpline.com.

@ln Lingála | wiki=ln | schrift=latin
hallo = mbote; mbote na yo; mbote na bino; mbote mingi
info = ozali nani; okoki kosala nini; lisalisi; salisa ngai
danke = matondi; melesi; matondi mingi; botondi
tschuess = tokomonana; kende malamu; tikala malamu; butu malamu
wiegehts = ozali malamu; sango nini; ndenge nini; boni
wetter = tango ya mokolo; mopepe; mbula; molunge
zeit = ngonga boni; ngonga ya boni; ezali ngonga boni
datum = lelo ezali mokolo nini; dati ya lelo; lelo mokolo boni
heute = lelo
morgen = lobi
wiki = nini ezali {x}; {x} ezali nini; {x} azali nani; yebisa ngai na ntina ya {x}
stopp = na; ya; o; ndenge; nini; lelo; lobi; ezali; ekozala; boni
krise = komiboma; nalingi kokufa
A.intro = Mbote! Nazali Aquaticy Standard. Nakoki koyebisa yo tango ya mokolo, ngonga mpe dati,
  kosala calcul mpe koluka na Wikipedia.
A.danke = Likambo te!
A.tschuess = Tokomonana!
A.wiegehts = Nazali malamu, matondi! Nakoki kosalisa yo na nini?
A.zeit = Sikoyo ezali ngonga {zeit}.
A.datum = Lelo ezali {datum}.
A.ort = Natala tango ya esika nini?
A.nichts = Bolimbisi, namoni eloko te na ntina ya “{x}”.
A.rueckfall = Bolimbisi, nakoki koyanola yango te soki modèle ya monoko ezali te. Tuna ngai na
  ntina ya tango, ngonga, dati, calcul to eloko moko ya Wikipedia.
A.krise = Ozali yo moko te. Soki ozali kokanisa kosilisa bomoi na yo, solola na moto sikoyo:
  benga nimero ya likama ya mboka na yo to luka lisalisi ya ofele na https://findahelpline.com.

@or ଓଡ଼ିଆ | wiki=or | schrift=oriya
hallo = ନମସ୍କାର; ହେଲୋ; ସୁପ୍ରଭାତ
info = ତୁମେ କିଏ; ଆପଣ କିଏ; ତୁମେ କଣ କରିପାରିବ; ସାହାଯ୍ୟ
danke = ଧନ୍ୟବାଦ; ବହୁତ ଧନ୍ୟବାଦ
tschuess = ବିଦାୟ; ପୁଣି ଦେଖା ହେବ; ଶୁଭ ରାତ୍ରି
wiegehts = ଆପଣ କେମିତି ଅଛନ୍ତି; କେମିତି ଅଛ; ଭଲ ଅଛ
wetter = ପାଣିପାଗ; ତାପମାତ୍ରା; ବର୍ଷା
zeit = କେତେ ବାଜିଲା; ସମୟ କେତେ; ଏବେ କେତେ ବାଜିଲା
datum = ଆଜି କେଉଁ ତାରିଖ; ଆଜିର ତାରିଖ; ଆଜି କି ବାର
heute = ଆଜି
morgen = କାଲି
wiki = {x} କଣ; {x} କ'ଣ; {x} କିଏ; {x} ବିଷୟରେ କୁହ
stopp = ରେ; ର; କେମିତି; କଣ; ଅଛି; ରହିବ; ଆଜି; କାଲି; କୁହ
krise = ଆତ୍ମହତ୍ୟା; ମରିବାକୁ ଚାହେଁ
A.intro = ନମସ୍କାର! ମୁଁ Aquaticy Standard। ମୁଁ ଆପଣଙ୍କୁ ପାଣିପାଗ, ସମୟ ଓ ତାରିଖ କହିପାରିବି, ହିସାବ
  କରିପାରିବି ଏବଂ ଉଇକିପିଡ଼ିଆରେ ଖୋଜିପାରିବି।
A.danke = ସ୍ୱାଗତ!
A.tschuess = ପୁଣି ଦେଖା ହେବ!
A.wiegehts = ମୁଁ ଭଲ ଅଛି, ଧନ୍ୟବାଦ! ମୁଁ କିପରି ସାହାଯ୍ୟ କରିବି?
A.zeit = ଏବେ {zeit}।
A.datum = ଆଜି {datum}।
A.ort = କେଉଁ ସ୍ଥାନର ପାଣିପାଗ ଦେଖିବି?
A.nichts = କ୍ଷମା କରନ୍ତୁ, “{x}” ବିଷୟରେ କିଛି ମିଳିଲା ନାହିଁ।
A.rueckfall = କ୍ଷମା କରନ୍ତୁ, ଭାଷା ମଡେଲ ବିନା ମୁଁ ଏହାର ଉତ୍ତର ଦେଇପାରିବି ନାହିଁ। ପାଣିପାଗ, ସମୟ,
  ତାରିଖ, ହିସାବ କିମ୍ବା ଉଇକିପିଡ଼ିଆ ବିଷୟରେ ପଚାରନ୍ତୁ।
A.krise = ଆପଣ ଏକା ନୁହଁନ୍ତି। ଯଦି ନିଜ ଜୀବନ ଶେଷ କରିବା କଥା ଭାବୁଛନ୍ତି, ଏବେ କାହା ସହ କଥା ହୁଅନ୍ତୁ:
  ଆପଣଙ୍କ ଦେଶର ଜରୁରୀକାଳୀନ ନମ୍ବରକୁ ଫୋନ କରନ୍ତୁ କିମ୍ବା https://findahelpline.com ରେ ମାଗଣା
  ହେଲ୍ପଲାଇନ ଖୋଜନ୍ତୁ।

@ml മലയാളം | wiki=ml | schrift=malayalam
hallo = നമസ്കാരം; ഹലോ; സുപ്രഭാതം; ഹായ്
info = നീ ആരാണ്; നിങ്ങൾ ആരാണ്; നിനക്ക് എന്ത് ചെയ്യാൻ കഴിയും; സഹായം
danke = നന്ദി; വളരെ നന്ദി; താങ്ക്സ്
tschuess = വിട; വീണ്ടും കാണാം; ശുഭരാത്രി; ബൈ
wiegehts = സുഖമാണോ; എങ്ങനെയുണ്ട്; എന്തൊക്കെയുണ്ട്
wetter = കാലാവസ്ഥ; താപനില; മഴ
zeit = സമയം എത്രയായി; മണി എത്രയായി; ഇപ്പോൾ സമയം എത്ര
datum = ഇന്ന് എത്രാം തീയതി; ഇന്നത്തെ തീയതി; ഇന്ന് ഏത് ദിവസം
heute = ഇന്ന്
morgen = നാളെ
wiki = {x} എന്താണ്; {x} ആരാണ്; {x} എന്നാൽ എന്ത്; {x} കുറിച്ച് പറയൂ
stopp = ൽ; ലെ; എങ്ങനെ; എന്താണ്; ഉണ്ട്; ആയിരിക്കും; ഇന്ന്; നാളെ; പറയൂ
krise = ആത്മഹത്യ; മരിക്കണം; മരിക്കാൻ തോന്നുന്നു
A.intro = നമസ്കാരം! ഞാൻ Aquaticy Standard ആണ്. എനിക്ക് കാലാവസ്ഥ, സമയം, തീയതി എന്നിവ പറയാനും
  കണക്കുകൂട്ടാനും വിക്കിപീഡിയയിൽ തിരയാനും കഴിയും.
A.danke = സ്വാഗതം!
A.tschuess = വീണ്ടും കാണാം!
A.wiegehts = എനിക്ക് സുഖമാണ്, നന്ദി! ഞാൻ എങ്ങനെ സഹായിക്കാം?
A.zeit = ഇപ്പോൾ സമയം {zeit}.
A.datum = ഇന്ന് {datum}.
A.ort = ഏത് സ്ഥലത്തെ കാലാവസ്ഥ നോക്കണം?
A.nichts = ക്ഷമിക്കണം, “{x}” കുറിച്ച് ഒന്നും കണ്ടെത്തിയില്ല.
A.rueckfall = ക്ഷമിക്കണം, ഭാഷാ മോഡൽ ഇല്ലാതെ എനിക്ക് ഇതിന് ഉത്തരം നൽകാൻ കഴിയില്ല. കാലാവസ്ഥ,
  സമയം, തീയതി, കണക്ക് അല്ലെങ്കിൽ വിക്കിപീഡിയയെക്കുറിച്ച് ചോദിക്കൂ.
A.krise = നിങ്ങൾ ഒറ്റയ്ക്കല്ല. ജീവിതം അവസാനിപ്പിക്കാൻ ആലോചിക്കുന്നുണ്ടെങ്കിൽ ഇപ്പോൾ തന്നെ
  ആരോടെങ്കിലും സംസാരിക്കൂ: നിങ്ങളുടെ രാജ്യത്തെ അടിയന്തര നമ്പറിൽ വിളിക്കൂ അല്ലെങ്കിൽ
  https://findahelpline.com ൽ സൗജന്യ ഹെൽപ്\u200cലൈൻ കണ്ടെത്തൂ.

@mai मैथिली | wiki=mai | schrift=devanagari
hallo = प्रणाम; गोड़ लगैत छी; नमस्कार जी
info = अहाँ के छी; अहाँ की क' सकैत छी; मदति
danke = धन्यवाद छी; बहुत धन्यवाद छी
tschuess = फेर भेंट होयत; जाइत छी; शुभ राति
wiegehts = अहाँ केहन छी; की हाल अछि; सब ठीक अछि
wetter = मौसम केहन अछि; मौसम अछि; बरखा
zeit = कतेक बजल अछि; समय की भेल; कतेक बजल
datum = आइ कोन तारीख अछि; आइक तारीख; आइ कोन दिन अछि
heute = आइ
morgen = काल्हि
wiki = {x} की अछि; {x} के छथि; {x} के बारेमे कहू
stopp = मे; केर; केहन; अछि; रहत; आइ; काल्हि; कहू
krise = आत्महत्या; मरबाक मन; मरए चाहैत छी
A.intro = प्रणाम! हम Aquaticy Standard छी। हम अहाँकेँ मौसम, समय आ तारीख कहि सकैत छी, हिसाब क'
  सकैत छी आ विकिपीडियापर ताकि सकैत छी।
A.danke = कोनो बात नहि!
A.tschuess = फेर भेंट होयत!
A.wiegehts = हम ठीक छी, धन्यवाद! हम अहाँक की मदति करू?
A.zeit = एखन {zeit} बजल अछि।
A.datum = आइ {datum} अछि।
A.ort = कोन ठामक मौसम देखू?
A.nichts = माफ करू, “{x}” केर बारेमे किछु नहि भेटल।
A.rueckfall = माफ करू, भाषा मॉडल बिना हम एकर उत्तर नहि द' सकैत छी। हमरासँ मौसम, समय, तारीख,
  हिसाब वा विकिपीडियाक बारेमे पूछू।
A.krise = अहाँ असगर नहि छी। जँ अपन जान लेबाक विचार आबि रहल अछि त' एखने ककरोसँ बात करू: अपन
  देशक आपातकालीन नंबरपर फोन करू वा https://findahelpline.com पर मुफ्त हेल्पलाइन ताकू।

@uz Oʻzbekcha | wiki=uz | schrift=latin,cyrillic
hallo = salom; assalomu alaykum; xayrli tong; xayrli kun; xayrli kech
info = sen kimsan; siz kimsiz; nima qila olasan; nima qila olasiz; yordam
danke = rahmat; katta rahmat; tashakkur
tschuess = xayr; ko'rishguncha; xayrli tun
wiegehts = qalaysan; qalaysiz; yaxshimisiz; ishlar qalay; нима гап
wetter = ob-havo; ob havo; harorat; yomg'ir; об-ҳаво
zeit = soat necha; hozir soat necha; vaqt qancha; соат неча
datum = bugun qaysi sana; bugungi sana; bugun nechanchi; bugun qaysi kun
heute = bugun
morgen = ertaga
wiki = {x} nima; {x} kim; {x} haqida aytib ber
stopp = da; dagi; qanday; nima; bugun; ertaga; bo'ladi; hozir; ayt; aytib
krise = o'zimni o'ldirmoqchiman; o'lishni xohlayman; o'z joniga qasd
A.intro = Salom! Men Aquaticy Standardman. Ob-havo, vaqt va sanani ayta olaman, hisoblay olaman va
  Vikipediyadan qidira olaman.
A.danke = Arzimaydi!
A.tschuess = Xayr! Ko'rishguncha.
A.wiegehts = Yaxshiman, rahmat! Sizga qanday yordam bera olaman?
A.zeit = Hozir soat {zeit}.
A.datum = Bugun {datum}.
A.ort = Qaysi joyning ob-havosini ko'ray?
A.nichts = Kechirasiz, “{x}” haqida hech narsa topmadim.
A.rueckfall = Kechirasiz, til modelisiz bunga javob bera olmayman. Mendan ob-havo, vaqt, sana,
  hisob yoki Vikipediyadagi biror narsa haqida so'rang.
A.krise = Siz yolg'iz emassiz. Agar o'z hayotingizga nuqta qo'yishni o'ylayotgan bo'lsangiz, hoziroq
  kimgadir gapiring: mamlakatingizdagi favqulodda raqamga qo'ng'iroq qiling yoki
  https://findahelpline.com saytidan bepul yordam liniyasini toping.

@sd سنڌي | wiki=sd | schrift=arabic
zeichen = ڪ;ڏ;ڙ;ٺ;ٽ;ڃ;ڄ;ڇ;ڻ;ڳ;ڱ
hallo = سلام; اسلام عليڪم; ڀلي ڪري آيا; صبح بخير
info = تون ڪير آهين; توهان ڪير آهيو; تون ڇا ڪري سگهين ٿو; مدد
danke = مهرباني; ٿورا; وڏي مهرباني; شڪريو
tschuess = خدا حافظ; الله واهي; وري ملنداسين
wiegehts = ڪيئن آهيو; ڪيئن آهين; ڇا حال آهي; خير آهي
wetter = موسم; گرمي پد; مينهن
zeit = ڪيترا وڳا آهن; ڪيترا وڳا; وقت ڇا آهي
datum = اڄ ڪهڙي تاريخ آهي; اڄ جي تاريخ; اڄ ڪهڙو ڏينهن آهي
heute = اڄ
morgen = سڀاڻي
wiki = {x} ڇا آهي; {x} ڪير آهي; {x} بابت ٻڌايو
stopp = ۾; جو; جي; ڪيئن; ڇا; آهي; هوندو; اڄ; سڀاڻي; ٻڌايو
krise = خودڪشي; مرڻ ٿو چاهيان; پاڻ کي ماري
A.intro = سلام! مان Aquaticy Standard آهيان. مان توهان کي موسم، وقت ۽ تاريخ ٻڌائي سگهان ٿو،
  حساب ڪري سگهان ٿو ۽ وڪيپيڊيا تي ڳولي سگهان ٿو.
A.danke = ڀلي ڪري آيا!
A.tschuess = خدا حافظ! وري ملنداسين.
A.wiegehts = مان ٺيڪ آهيان، مهرباني! مان توهان جي ڪهڙي مدد ڪريان؟
A.zeit = هن وقت {zeit} وڳا آهن.
A.datum = اڄ {datum} آهي.
A.ort = ڪهڙي هنڌ جي موسم ڏسان؟
A.nichts = معاف ڪجو، “{x}” بابت ڪجهه نه مليو.
A.rueckfall = معاف ڪجو، ٻوليءَ جي ماڊل کان سواءِ مان ان جو جواب نٿو ڏئي سگهان. مون کان موسم، وقت،
  تاريخ، حساب يا وڪيپيڊيا بابت پڇو.
A.krise = توهان اڪيلا نه آهيو. جيڪڏهن توهان پنهنجي زندگي ختم ڪرڻ جو سوچي رهيا آهيو ته هاڻي ئي ڪنهن
  سان ڳالهايو: پنهنجي ملڪ جي ايمرجنسي نمبر تي ڪال ڪريو يا https://findahelpline.com تي مفت
  هيلپ لائين ڳوليو.

@uk Українська | wiki=uk | schrift=cyrillic
zeichen = і;ї;є;ґ
hallo = привіт; добрий день; доброго дня; вітаю; доброго ранку; добрий вечір
info = хто ти; хто ви; що ти вмієш; що ти можеш; допомога; допоможи
danke = дякую; щиро дякую; дуже дякую; спасибі
tschuess = бувай; до побачення; на все добре; добраніч; па-па
wiegehts = як справи; як ти; як у тебе справи; як ся маєш
wetter = погода; яка погода; погоду; погоди; прогноз погоди; температура; дощ
zeit = котра година; скільки часу; котра зараз година
datum = яке сьогодні число; яка сьогодні дата; яке число; який сьогодні день
heute = сьогодні
morgen = завтра
wiki = що таке {x}; хто такий {x}; хто така {x}; хто був {x}; розкажи про {x}
stopp = в; у; на; для; яка; який; як; буде; сьогодні; завтра; зараз; скажи; будь; ласка
krise = покінчити з собою; хочу померти; вбити себе; самогубство
A.intro = Привіт! Я Aquaticy Standard. Я можу сказати погоду, час і дату, порахувати й пошукати
  у Вікіпедії.
A.danke = Будь ласка!
A.tschuess = До побачення! До зустрічі.
A.wiegehts = У мене все добре, дякую! Чим можу допомогти?
A.zeit = Зараз {zeit}.
A.datum = Сьогодні {datum}.
A.ort = Для якого місця показати погоду?
A.nichts = Вибачте, я нічого не знайшов про «{x}».
A.rueckfall = Вибачте, без мовної моделі я не можу на це відповісти. Запитайте мене про погоду,
  час, дату, обчислення або щось із Вікіпедії.
A.krise = Ви не самі. Якщо ви думаєте про те, щоб покінчити з життям, поговоріть з кимось просто
  зараз: зателефонуйте на місцевий екстрений номер або знайдіть безкоштовну лінію допомоги на
  https://findahelpline.com.

@ne नेपाली | wiki=ne | schrift=devanagari
hallo = नमस्ते; नमस्कार; हजुर नमस्ते; शुभ प्रभात
info = तिमी को हौ; तपाईं को हुनुहुन्छ; तिमी के गर्न सक्छौ; तपाईं के गर्न सक्नुहुन्छ; सहयोग
danke = धन्यवाद छ; धेरै धन्यवाद; धन्यवाद हजुर
tschuess = फेरि भेटौंला; बिदा; शुभ रात्री
wiegehts = तपाईंलाई कस्तो छ; सन्चै हुनुहुन्छ; के छ खबर; कस्तो छ
wetter = मौसम कस्तो छ; मौसम; तापक्रम; पानी पर्छ
zeit = कति बज्यो; अहिले कति बज्यो; समय कति भयो
datum = आज कति गते हो; आजको मिति; आज कुन बार हो
heute = आज
morgen = भोलि
wiki = {x} के हो; {x} को हो; {x} को बारेमा भन
stopp = मा; को; कस्तो; के; छ; हुन्छ; आज; भोलि; भन्नुहोस्; भन
krise = आत्महत्या; मर्न मन लाग्यो; मर्न चाहन्छु
A.intro = नमस्ते! म Aquaticy Standard हुँ। म तपाईंलाई मौसम, समय र मिति भन्न, हिसाब गर्न र
  विकिपिडियामा खोज्न सक्छु।
A.danke = स्वागत छ!
A.tschuess = फेरि भेटौंला!
A.wiegehts = म सन्चै छु, धन्यवाद! म तपाईंलाई कसरी सहयोग गरूँ?
A.zeit = अहिले {zeit} बज्यो।
A.datum = आज {datum} हो।
A.ort = कुन ठाउँको मौसम हेरूँ?
A.nichts = माफ गर्नुहोस्, “{x}” बारे केही भेटिएन।
A.rueckfall = माफ गर्नुहोस्, भाषा मोडेल बिना म यसको जवाफ दिन सक्दिनँ। मलाई मौसम, समय, मिति,
  हिसाब वा विकिपिडियाबारे सोध्नुहोस्।
A.krise = तपाईं एक्लो हुनुहुन्न। यदि आफ्नो जीवन अन्त्य गर्ने सोच आइरहेको छ भने अहिल्यै कसैसँग
  कुरा गर्नुहोस्: आफ्नो देशको आपतकालीन नम्बरमा फोन गर्नुहोस् वा https://findahelpline.com मा
  निःशुल्क हेल्पलाइन खोज्नुहोस्।

@ro Română | wiki=ro | schrift=latin
zeichen = ă;ș;ț;ş;ţ
hallo = salut; bună; bună ziua; bună dimineața; bună seara; servus
info = cine ești; ce poți face; ce știi să faci; ajutor
danke = mulțumesc; mersi; mulțumesc mult; mulțumiri
tschuess = la revedere; pa; ne vedem; noapte bună; pe curând
wiegehts = ce faci; ce mai faci; cum ești; cum te simți
wetter = vremea; vreme; prognoza meteo; temperatura; plouă; ploaie
zeit = cât e ceasul; ce oră este; cât este ora
datum = ce dată este azi; ce zi e azi; data de azi; în ce dată suntem
heute = azi
morgen = mâine
wiki = ce este {x}; cine este {x}; cine a fost {x}; spune-mi despre {x}
stopp = în; la; din; pentru; cum; e; este; va; fi; azi; astăzi; mâine; acum; spune-mi; ce
krise = să mă sinucid; vreau să mor; să mă omor; sinucidere
A.intro = Salut! Sunt Aquaticy Standard. Îți pot spune vremea, ora și data, pot face calcule și
  pot căuta pe Wikipedia.
A.danke = Cu plăcere!
A.tschuess = La revedere! Pe curând.
A.wiegehts = Sunt bine, mulțumesc! Cu ce te pot ajuta?
A.zeit = Este ora {zeit}.
A.datum = Azi este {datum}.
A.ort = Pentru ce loc vrei vremea?
A.nichts = Îmi pare rău, n-am găsit nimic despre „{x}”.
A.rueckfall = Îmi pare rău, fără un model de limbaj nu pot răspunde la asta. Întreabă-mă despre
  vreme, oră, dată, un calcul sau ceva de pe Wikipedia.
A.krise = Nu ești singur. Dacă te gândești să-ți iei viața, vorbește cu cineva acum: sună la
  numărul de urgență din țara ta sau găsește o linie de ajutor gratuită pe
  https://findahelpline.com.

@zu isiZulu | wiki=zu | schrift=latin
hallo = sawubona; sanibonani; sawubona mngane; yebo sawubona
info = ungubani; ungenzani; yini ongayenza; usizo; ngisize
danke = ngiyabonga; ngiyabonga kakhulu; siyabonga
tschuess = sala kahle; hamba kahle; sobonana; ulale kahle
wiegehts = unjani; ninjani; usaphila; kunjani
wetter = isimo sezulu; izulu; ukushisa; imvula
zeit = yisikhathi sini; sithini isikhathi; isikhathi sini manje
datum = usuku luni namuhla; namuhla kungumhla bani; usuku lwanamuhla
heute = namuhla
morgen = kusasa
wiki = yini {x}; ungubani {x}; ngitshele ngo {x}; kuyini {x}
stopp = e; ku; kwa; kanjani; namuhla; kusasa; manje; sezulu; isimo; kuzoba
krise = ukuzibulala; ngifuna ukufa
A.intro = Sawubona! NginguAquaticy Standard. Ngingakutshela isimo sezulu, isikhathi nosuku,
  ngibale futhi ngicinge kuWikipedia.
A.danke = Wamukelekile!
A.tschuess = Sala kahle! Sobonana.
A.wiegehts = Ngiyaphila, ngiyabonga! Ngingakusiza ngani?
A.zeit = Manje yisikhathi {zeit}.
A.datum = Namuhla ngu-{datum}.
A.ort = Ngibheke isimo sezulu sasiphi?
A.nichts = Uxolo, angitholanga lutho mayelana no-“{x}”.
A.rueckfall = Uxolo, angikwazi ukuphendula lokho ngaphandle kwemodeli yolimi. Ngibuze ngesimo
  sezulu, isikhathi, usuku, ukubala noma okuthile okuvela kuWikipedia.
A.krise = Awuwedwa. Uma ucabanga ukuziqeda impilo, sicela ukhulume nomuntu manje: shayela inombolo
  yezimo eziphuthumayo ezweni lakho noma uthole usizo lwamahhala ku-https://findahelpline.com.

@ig Igbo | wiki=ig | schrift=latin
zeichen = ị;ụ
hallo = ndewo; nnọọ; kedu; ụtụtụ ọma; mgbede ọma; ndeewo
info = onye ka ị bụ; gịnị ka ị nwere ike ime; enyemaka; nyere m aka
danke = daalụ; dalu; imela; daalụ nke ukwuu
tschuess = ka ọ dị; ka emesịa; ka chi bọọ; ka ọ dị echi
wiegehts = kedu ka ị mere; kedụ; i di mma; ọ dị mma
wetter = ọnọdụ ihu igwe; ihu igwe; okpomọkụ; mmiri ozuzo
zeit = kedu oge ọ bụ; oge ole ka ọ bụ; elekere ole
datum = ụbọchị ole ka taa bụ; ụbọchị taa; kedu ụbọchị taa
heute = taa
morgen = echi
wiki = gịnị bụ {x}; onye bụ {x}; gwa m maka {x}
stopp = na; nke; kedu; taa; echi; ga; dị; bụ; ugbu a
krise = igbu onwe m; achọrọ m ịnwụ
A.intro = Ndewo! Abụ m Aquaticy Standard. Enwere m ike ịgwa gị ihu igwe, oge na ụbọchị, gụọ
  ọnụ ọgụgụ ma chọọ ihe na Wikipedia.
A.danke = Ọ dịghị nsogbu!
A.tschuess = Ka ọ dị! Ka emesịa.
A.wiegehts = Adị m mma, daalụ! Kedu ka m ga-esi nyere gị aka?
A.zeit = Ugbu a bụ {zeit}.
A.datum = Taa bụ {datum}.
A.ort = Ihu igwe ebee ka m lee?
A.nichts = Ndo, ahụghị m ihe ọ bụla gbasara “{x}”.
A.rueckfall = Ndo, enweghị m ike ịza nke ahụ na-enweghị ụdị asụsụ. Jụọ m maka ihu igwe, oge,
  ụbọchị, mgbakọ ma ọ bụ ihe sitere na Wikipedia.
A.krise = Ị nọghị naanị gị. Ọ bụrụ na ị na-eche ịkwụsị ndụ gị, biko gwa mmadụ okwu ugbu a: kpọọ
  nọmba ihe mberede nke obodo gị ma ọ bụ chọta enyemaka n'efu na https://findahelpline.com.

@nl Nederlands | wiki=nl | schrift=latin
hallo = hallo; hoi; goedemorgen; goedemiddag; goedenavond; dag; hey
info = wie ben jij; wie ben je; wat kun je; wat kun jij doen; help; hulp
danke = dank je; dank je wel; bedankt; dank u wel; hartelijk dank
tschuess = doei; tot ziens; dag dag; tot later; welterusten; doeg
wiegehts = hoe gaat het; hoe gaat het met je; alles goed; hoe is het
wetter = weer; het weer; wat voor weer; weerbericht; temperatuur; regent; regen; regenen
zeit = hoe laat is het; hoe laat; de tijd
datum = welke datum is het; wat is de datum; welke dag is het; de datum van vandaag
heute = vandaag
morgen = morgen
wiki = wat is {x}; wie is {x}; wie was {x}; vertel me over {x}
stopp = in; op; voor; het; de; hoe; is; wordt; vandaag; morgen; nu; wat; zal; weer;
  gaat; regenen; regent
krise = zelfmoord; ik wil dood; mezelf van kant maken; mezelf doden
A.intro = Hallo! Ik ben Aquaticy Standard. Ik kan je het weer, de tijd en de datum vertellen,
  rekenen en op Wikipedia zoeken.
A.danke = Graag gedaan!
A.tschuess = Tot ziens!
A.wiegehts = Goed, dank je! Waarmee kan ik je helpen?
A.zeit = Het is {zeit}.
A.datum = Vandaag is het {datum}.
A.ort = Voor welke plaats wil je het weer weten?
A.nichts = Sorry, ik heb niets gevonden over „{x}”.
A.rueckfall = Sorry, zonder taalmodel kan ik daar geen antwoord op geven. Vraag me naar het weer,
  de tijd, de datum, een berekening of iets van Wikipedia.
A.krise = Je bent niet alleen. Als je erover denkt een einde aan je leven te maken, praat dan nu
  met iemand: bel het noodnummer in je land of vind een gratis hulplijn op
  https://findahelpline.com.

@so Soomaali | wiki=so | schrift=latin
hallo = salaan; iska warran; nabad; subax wanaagsan; galab wanaagsan; asalaamu calaykum
info = yaad tahay; maxaad samayn kartaa; caawimaad; i caawi
danke = mahadsanid; mahadsanid aad; aad baad u mahadsantahay
tschuess = nabad gelyo; nabadgelyo; is arag dambe; habeen wanaagsan
wiegehts = sidee tahay; ma nabad baa; ka warran; ma fiican tahay
wetter = cimilada; cimilo; heerkulka; roob
zeit = waa imisa saacaddu; saacaddu waa imisa; waqtiga
datum = maanta waa taariikhdee; taariikhda maanta; maanta waa maalintee
heute = maanta
morgen = berri
wiki = waa maxay {x}; muxuu yahay {x}; waa kuma {x}; ii sheeg {x}
stopp = ee; ka; ku; sidee; maanta; berri; waa; noqon; hadda
krise = is dilid; waxaan rabaa inaan dhinto; naftayda dil
A.intro = Salaan! Waxaan ahay Aquaticy Standard. Waxaan kuu sheegi karaa cimilada, waqtiga iyo
  taariikhda, waan xisaabin karaa oo waan ka raadin karaa Wikipedia.
A.danke = Adaa mudan!
A.tschuess = Nabad gelyo!
A.wiegehts = Waan fiicnahay, mahadsanid! Sideen kuu caawin karaa?
A.zeit = Hadda waa {zeit}.
A.datum = Maanta waa {datum}.
A.ort = Cimilada meeqay ah ayaan eegaa?
A.nichts = Waan ka xumahay, waxba kama helin “{x}”.
A.rueckfall = Waan ka xumahay, kama jawaabi karo taas la'aan nidaam luqadeed. I weydii cimilada,
  waqtiga, taariikhda, xisaab ama wax ka mid ah Wikipedia.
A.krise = Keligaa ma tihid. Haddii aad ka fikireyso inaad naftaada dhammayso, fadlan hadda la
  hadal qof: wac lambarka degdegga ah ee dalkaaga ama ka hel khad caawimaad oo bilaash ah
  https://findahelpline.com.

@ps پښتو | wiki=ps | schrift=arabic
zeichen = ټ;ډ;ړ;ښ;ږ;ځ;څ;ۍ
hallo = سلام; السلام علیکم; ستړي مه شې; پخير راغلې; سهار مو پخير
info = ته څوک یې; تاسو څوک یاست; ته څه کولی شې; مرسته
danke = مننه; ډېره مننه; تشکر
tschuess = په مخه دې ښه; خدای پامان; بیا به سره ووینو; شپه مو پخير
wiegehts = څنګه یې; ته څنګه یې; ښه یې; جوړ یې
wetter = هوا; د هوا حالت; تودوخه; باران
zeit = څو بجې دي; اوس څو بجې دي; وخت څه دی
datum = نن څو نېټه ده; د نن نېټه; نن کومه ورځ ده
heute = نن
morgen = سبا
wiki = {x} څه شی دی; {x} څه دی; {x} څوک دی; د {x} په اړه ووایه
stopp = په; کې; د; څنګه; دی; ده; به; وي; نن; سبا; اوس; ووایه
krise = ځان وژنه; غواړم چې مړ شم; ځان ووژنم
A.intro = سلام! زه Aquaticy Standard یم. زه تاسو ته هوا، وخت او نېټه ویلی شم، حساب کولی شم او
  په ويکيپېډيا کې لټون کولی شم.
A.danke = هرکله!
A.tschuess = په مخه دې ښه!
A.wiegehts = زه ښه یم، مننه! څنګه مرسته درسره وکړم؟
A.zeit = اوس {zeit} بجې دي.
A.datum = نن {datum} ده.
A.ort = د کوم ځای هوا وګورم؟
A.nichts = بښنه غواړم، د «{x}» په اړه مې څه ونه موندل.
A.rueckfall = بښنه غواړم، د ژبې ماډل پرته زه دې ته ځواب نه شم ورکولی. له ما څخه د هوا، وخت،
  نېټې، حساب یا ويکيپېډيا په اړه وپوښتئ.
A.krise = تاسو یوازې نه یاست. که د خپل ژوند پای ته رسولو فکر کوئ، همدا اوس له چا سره خبرې
  وکړئ: د خپل هېواد بیړني شمېرې ته زنګ ووهئ یا په https://findahelpline.com کې وړیا د مرستې
  کرښه ومومئ.

@ms Bahasa Melayu | wiki=ms | schrift=latin
hallo = helo; hai; selamat pagi; selamat petang; selamat malam; assalamualaikum
info = siapa awak; awak siapa; apa yang awak boleh buat; boleh buat apa; bantuan
danke = terima kasih; terima kasih banyak; ribuan terima kasih
tschuess = selamat tinggal; jumpa lagi; selamat jalan; bye
wiegehts = apa khabar; khabar baik; bagaimana keadaan awak; sihat
wetter = cuaca; ramalan cuaca; suhu; hujan
zeit = pukul berapa; pukul berapa sekarang; jam berapa sekarang
datum = hari ini berapa haribulan; tarikh hari ini; hari ini hari apa
heute = hari ini
morgen = esok
wiki = apa itu {x}; siapa {x}; ceritakan tentang {x}; apakah {x}
stopp = di; ke; untuk; bagaimana; apa; macam; akan; hari; ini; esok; sekarang; yang
krise = bunuh diri; nak mati; mahu mati; tamatkan hidup
A.intro = Helo! Saya Aquaticy Standard. Saya boleh memberitahu cuaca, masa dan tarikh, mengira
  dan mencari di Wikipedia.
A.danke = Sama-sama!
A.tschuess = Selamat tinggal! Jumpa lagi.
A.wiegehts = Saya sihat, terima kasih! Apa yang boleh saya bantu?
A.zeit = Sekarang pukul {zeit}.
A.datum = Hari ini {datum}.
A.ort = Cuaca di tempat mana yang hendak saya semak?
A.nichts = Maaf, saya tidak menjumpai apa-apa tentang “{x}”.
A.rueckfall = Maaf, tanpa model bahasa saya tidak dapat menjawabnya. Tanya saya tentang cuaca,
  masa, tarikh, pengiraan atau sesuatu dari Wikipedia.
A.krise = Anda tidak keseorangan. Jika anda terfikir untuk menamatkan hidup, sila bercakap dengan
  seseorang sekarang: hubungi nombor kecemasan negara anda atau cari talian bantuan percuma di
  https://findahelpline.com.

@su Basa Sunda | wiki=su | schrift=latin
hallo = sampurasun; wilujeng enjing; wilujeng siang; wilujeng wengi; kumaha damang
info = saha anjeun; anjeun tiasa naon; bisa naon; pitulung
danke = hatur nuhun; nuhun; hatur nuhun pisan
tschuess = dugi ka pendak deui; pamit; mangga
wiegehts = kumaha damang; kumaha kabarna; pangestu
wetter = cuaca; hawa; hujan; suhu
zeit = jam sabaraha; ayeuna jam sabaraha
datum = tanggal sabaraha; dinten naon ayeuna; tanggal ayeuna
heute = ayeuna
morgen = isukan
wiki = naon ari {x}; naon éta {x}; saha {x}; caritakeun ngeunaan {x}
stopp = di; ka; kumaha; naon; ayeuna; isukan; bakal; téh
krise = bunuh diri; hoyong maot
A.intro = Sampurasun! Abdi Aquaticy Standard. Abdi tiasa nyarioskeun cuaca, waktos sareng tanggal,
  ngitung sareng milarian di Wikipedia.
A.danke = Sami-sami!
A.tschuess = Dugi ka pendak deui!
A.wiegehts = Pangestu, hatur nuhun! Naon anu tiasa abdi bantos?
A.zeit = Ayeuna jam {zeit}.
A.datum = Dinten ieu {datum}.
A.ort = Cuaca di tempat mana anu kedah abdi tingali?
A.nichts = Hapunten, abdi teu mendakan nanaon ngeunaan “{x}”.
A.rueckfall = Hapunten, tanpa modél basa abdi teu tiasa ngawaler éta. Taroskeun ngeunaan cuaca,
  waktos, tanggal, itungan atanapi hal tina Wikipedia.
A.krise = Anjeun henteu nyalira. Upami anjeun mikir pikeun ngeureunkeun hirup, mangga nyarios ka
  batur ayeuna: nelepon nomer darurat di nagara anjeun atanapi milarian layanan bantuan gratis di
  https://findahelpline.com.

@ff Fulfulde | wiki=ff | schrift=latin
zeichen = ɓ;ɗ;ŋ;ƴ
hallo = jam waali; jam na; no mbaɗa; jam weeti
info = a hono; ko mbaawɗa waɗde; ballal; wallu kam
danke = a jaaraama; a jaraama; jaraama; useko
tschuess = haa jango; en kawtan; jam waala
wiegehts = no mbaɗ-ɗaa; a selli na; no mbaɗa
wetter = weeyo; ndiyam ndungu; ngulndi
zeit = waktu ko hol; ko hol waktu; ko waktu
datum = hannde ko hol ñalawma; ñalawma hannde
heute = hannde
morgen = jango
wiki = ko woni {x}; hol {x}; holi ko {x}
stopp = e; to; nder; hannde; jango; no; ko; jooni
krise = warde hoore am; mi yiɗi maayde
A.intro = Jam waali! Miɗo Aquaticy Standard. Mbaawmi haalande ma weeyo, waktu e ñalawma, limde e
  yiylaade e Wikipedia.
A.danke = Alaa ko waɗi!
A.tschuess = Haa jango!
A.wiegehts = Mi selli, a jaaraama! Ko mbaawmi wallude ma?
A.zeit = Jooni ko {zeit}.
A.datum = Hannde ko {datum}.
A.ort = Weeyo nokku hol mi ƴeewa?
A.nichts = Yaafo, mi tawaani hay huunde e “{x}”.
A.rueckfall = Yaafo, mi waawaa jaabaade ɗum ko alaa modeel ɗemngal. Lamndo kam weeyo, waktu,
  ñalawma, limoore walla huunde e Wikipedia.
A.krise = A wonaa gooto. So a miijii hirde ngurndam maa, haal e neɗɗo jooni: noddu limoore
  caɗeele leydi maa walla yiy ballal ɗoon https://findahelpline.com.

@xh isiXhosa | wiki=xh | schrift=latin
hallo = molo; molweni; molo mhlobo; bhota
info = ungubani; ungenza ntoni; uncedo; ndincede
danke = enkosi; enkosi kakhulu; ndiyabulela
tschuess = sala kakuhle; hamba kakuhle; sobonana; ulale kakuhle
wiegehts = unjani; ninjani; kunjani; uphilile
wetter = imozulu; ubushushu; imvula
zeit = ngubani ixesha; lithini ixesha; ixesha lingakanani
datum = ngumhla bani namhlanje; umhla wanamhlanje; yintoni usuku namhlanje
heute = namhlanje
morgen = ngomso
wiki = yintoni {x}; ngubani {x}; ndixelele nge {x}
stopp = e; ku; kwa; njani; namhlanje; ngomso; ngoku; izakuba
krise = ukuzibulala; ndifuna ukufa
A.intro = Molo! NdinguAquaticy Standard. Ndingakuxelela imozulu, ixesha nomhla, ndibale kwaye
  ndikhangele kuWikipedia.
A.danke = Wamkelekile!
A.tschuess = Sala kakuhle!
A.wiegehts = Ndiphilile, enkosi! Ndingakunceda njani?
A.zeit = Ngoku lixesha {zeit}.
A.datum = Namhlanje ngu-{datum}.
A.ort = Ndijonge imozulu yeyiphi indawo?
A.nichts = Uxolo, andifumananga nto malunga no-“{x}”.
A.rueckfall = Uxolo, andikwazi ukuphendula oko ngaphandle kwemodeli yolwimi. Ndibuze ngemozulu,
  ixesha, umhla, ukubala okanye into evela kuWikipedia.
A.krise = Awukho wedwa. Ukuba ucinga ukuziphelisa ubomi, nceda uthethe nomntu ngoku: tsalela
  inombolo yongxamiseko yelizwe lakho okanye ufumane uncedo lwasimahla ku-https://findahelpline.com.

@si සිංහල | wiki=si | schrift=sinhala
hallo = ආයුබෝවන්; හලෝ; සුබ උදෑසනක්; සුබ සන්ධ්\u200dයාවක්
info = ඔයා කවුද; ඔබ කවුද; ඔයාට මොනවද කරන්න පුළුවන්; උදව්
danke = ස්තූතියි; බොහොම ස්තූතියි; තෑන්ක්ස්
tschuess = ගිහින් එන්නම්; ආයෙත් හමුවෙමු; සුබ රාත්\u200dරියක්; බායි
wiegehts = කොහොමද; ඔයාට කොහොමද; සැපසනීප කොහොමද
wetter = කාලගුණය; උෂ්ණත්වය; වැස්ස
zeit = වෙලාව කීයද; දැන් වෙලාව කීයද; වෙලාව
datum = අද දිනය කීයද; අද දිනය; අද මොන දවසද
heute = අද
morgen = හෙට
wiki = {x} යනු කුමක්ද; {x} කියන්නේ මොකක්ද; {x} කවුද; {x} ගැන කියන්න
stopp = හි; වල; කොහොමද; මොකක්ද; ද; වේද; අද; හෙට; කියන්න
krise = සියදිවි නසා; මැරෙන්න ඕනේ; මට මැරෙන්න ඕන
A.intro = ආයුබෝවන්! මම Aquaticy Standard. මට ඔබට කාලගුණය, වේලාව සහ දිනය කියන්න, ගණනය කරන්න සහ
  විකිපීඩියාවේ සොයන්න පුළුවන්.
A.danke = සාදරයෙන් පිළිගනිමු!
A.tschuess = ආයෙත් හමුවෙමු!
A.wiegehts = මට හොඳයි, ස්තූතියි! මම කොහොමද උදව් කරන්නේ?
A.zeit = දැන් වේලාව {zeit}.
A.datum = අද {datum}.
A.ort = කුමන ස්ථානයේ කාලගුණය බලන්නද?
A.nichts = සමාවන්න, “{x}” ගැන කිසිවක් හමු නොවීය.
A.rueckfall = සමාවන්න, භාෂා ආකෘතියක් නොමැතිව මට එයට පිළිතුරු දිය නොහැක. කාලගුණය, වේලාව, දිනය,
  ගණනය කිරීමක් හෝ විකිපීඩියාව ගැන අසන්න.
A.krise = ඔබ තනි නැහැ. ඔබේ ජීවිතය අවසන් කිරීමට සිතනවා නම්, දැන්ම කෙනෙකු සමඟ කතා කරන්න: ඔබේ රටේ
  හදිසි අංකයට අමතන්න හෝ https://findahelpline.com හි නොමිලේ උදව් සේවාවක් සොයන්න.

@km ខ្មែរ | wiki=km | schrift=khmer | nospace
hallo = សួស្តី; ជំរាបសួរ; អរុណសួស្តី
info = អ្នកជានរណា; តើអ្នកជានរណា; អ្នកអាចធ្វើអ្វីបាន; ជំនួយ
danke = អរគុណ; អរគុណច្រើន; សូមអរគុណ
tschuess = លាហើយ; ជួបគ្នាពេលក្រោយ; រាត្រីសួស្តី
wiegehts = សុខសប្បាយទេ; អ្នកសុខសប្បាយទេ; ម៉េចហើយ
wetter = អាកាសធាតុ; សីតុណ្ហភាព; ភ្លៀង
zeit = ម៉ោងប៉ុន្មាន; ឥឡូវម៉ោងប៉ុន្មាន; ម៉ោង
datum = ថ្ងៃនេះថ្ងៃទីប៉ុន្មាន; កាលបរិច្ឆេទ; ថ្ងៃនេះថ្ងៃអ្វី
heute = ថ្ងៃនេះ
morgen = ថ្ងៃស្អែក
wiki = {x}ជាអ្វី; តើ{x}ជាអ្វី; {x}ជានរណា
stopp = នៅ; របស់; យ៉ាងម៉េច; ដូចម្តេច; តើ; ថ្ងៃនេះ; ថ្ងៃស្អែក; ឥឡូវ; ទេ
krise = សម្លាប់ខ្លួន; ចង់ស្លាប់
A.intro = សួស្តី! ខ្ញុំជា Aquaticy Standard។ ខ្ញុំអាចប្រាប់អ្នកពីអាកាសធាតុ ម៉ោង និងកាលបរិច្ឆេទ
  គណនា និងស្វែងរកក្នុងវិគីភីឌា។
A.danke = មិនអីទេ!
A.tschuess = លាហើយ! ជួបគ្នាពេលក្រោយ។
A.wiegehts = ខ្ញុំសុខសប្បាយ អរគុណ! តើខ្ញុំអាចជួយអ្វីបាន?
A.zeit = ឥឡូវម៉ោង {zeit}។
A.datum = ថ្ងៃនេះ {datum}។
A.ort = ចង់ដឹងអាកាសធាតុនៅកន្លែងណា?
A.nichts = សូមទោស ខ្ញុំរកមិនឃើញអ្វីអំពី “{x}” ទេ។
A.rueckfall = សូមទោស បើគ្មានម៉ូដែលភាសា ខ្ញុំមិនអាចឆ្លើយបានទេ។ សូមសួរខ្ញុំពីអាកាសធាតុ ម៉ោង
  កាលបរិច្ឆេទ ការគណនា ឬអ្វីមួយពីវិគីភីឌា។
A.krise = អ្នកមិននៅម្នាក់ឯងទេ។ ប្រសិនបើអ្នកកំពុងគិតចង់បញ្ចប់ជីវិត សូមនិយាយជាមួយនរណាម្នាក់ឥឡូវនេះ៖
  ហៅលេខសង្គ្រោះបន្ទាន់នៅប្រទេសរបស់អ្នក ឬស្វែងរកខ្សែជំនួយឥតគិតថ្លៃនៅ https://findahelpline.com។

@as অসমীয়া | wiki=as | schrift=bengali
hallo = নমস্কাৰ; হেল' ; সুপ্ৰভাত
info = তুমি কোন; আপুনি কোন; তুমি কি কৰিব পাৰা; সহায়
danke = ধন্যবাদ দিলোঁ; বহুত ধন্যবাদ; ধন্যবাদ আপোনাক
tschuess = বিদায় দিয়ক; পুনৰ লগ পাম; শুভ ৰাত্ৰি
wiegehts = আপুনি কেনে আছে; কেনে আছা; ভালে আছানে
wetter = বতৰ; তাপমাত্ৰা; বৰষুণ
zeit = কিমান বাজিছে; এতিয়া কিমান বাজিছে; সময় কিমান
datum = আজি কিমান তাৰিখ; আজিৰ তাৰিখ; আজি কি বাৰ
heute = আজি
morgen = কাইলৈ
wiki = {x} কি; {x} কি হয়; {x} কোন; {x}ৰ বিষয়ে কোৱা
stopp = ত; ৰ; কেনে; কি; হ'ব; আজি; কাইলৈ; কোৱা
krise = আত্মহত্যা কৰিম; মৰিব বিচাৰো
A.intro = নমস্কাৰ! মই Aquaticy Standard। মই আপোনাক বতৰ, সময় আৰু তাৰিখ ক'ব পাৰোঁ, হিচাপ কৰিব পাৰোঁ
  আৰু ৱিকিপিডিয়াত বিচাৰিব পাৰোঁ।
A.danke = আদৰণি জনালোঁ!
A.tschuess = পুনৰ লগ পাম!
A.wiegehts = মই ভালে আছোঁ, ধন্যবাদ! মই কেনেকৈ সহায় কৰিব পাৰোঁ?
A.zeit = এতিয়া {zeit} বাজিছে।
A.datum = আজি {datum}।
A.ort = কোন ঠাইৰ বতৰ চাম?
A.nichts = ক্ষমা কৰিব, “{x}”ৰ বিষয়ে একো নাপালোঁ।
A.rueckfall = ক্ষমা কৰিব, ভাষা মডেল অবিহনে মই ইয়াৰ উত্তৰ দিব নোৱাৰোঁ। মোক বতৰ, সময়, তাৰিখ,
  হিচাপ বা ৱিকিপিডিয়াৰ বিষয়ে সোধক।
A.krise = আপুনি অকলশৰীয়া নহয়। যদি নিজৰ জীৱন শেষ কৰাৰ কথা ভাবিছে, এতিয়াই কাৰোবাৰ লগত কথা পাতক:
  আপোনাৰ দেশৰ জৰুৰীকালীন নম্বৰত ফোন কৰক বা https://findahelpline.com ত বিনামূলীয়া হেল্পলাইন
  বিচাৰক।

@hu Magyar | wiki=hu | schrift=latin
zeichen = ő;ű
hallo = szia; sziasztok; jó napot; jó reggelt; jó estét; helló; üdv
info = ki vagy; ki vagy te; mit tudsz; mit tudsz csinálni; segítség
danke = köszönöm; köszi; köszönöm szépen; nagyon köszönöm
tschuess = viszlát; viszontlátásra; jó éjszakát; szia később
wiegehts = hogy vagy; hogy van; mi újság; hogy s mint
wetter = időjárás; milyen az idő; idő; hőmérséklet; esik az eső
zeit = hány óra van; mennyi az idő; hány óra
datum = milyen nap van ma; hányadika van ma; mai dátum; hányadika van
heute = ma
morgen = holnap
wiki = mi az a {x}; mi a {x}; ki az a {x}; ki volt {x}; mesélj a {x}
stopp = az; a; ban; ben; ma; holnap; milyen; lesz; most; mi; van
endungen = ban; ben; on; en; ön; ra; re
krise = öngyilkos; meg akarok halni; megölöm magam
A.intro = Szia! Aquaticy Standard vagyok. Meg tudom mondani az időjárást, az időt és a dátumot,
  számolni tudok, és keresni a Wikipédián.
A.danke = Szívesen!
A.tschuess = Viszlát!
A.wiegehts = Jól vagyok, köszönöm! Miben segíthetek?
A.zeit = {zeit} van.
A.datum = Ma {datum} van.
A.ort = Melyik hely időjárását nézzem meg?
A.nichts = Sajnálom, nem találtam semmit erről: „{x}”.
A.rueckfall = Sajnálom, nyelvi modell nélkül erre nem tudok válaszolni. Kérdezz az időjárásról,
  az időről, a dátumról, egy számításról vagy valamiről a Wikipédiából.
A.krise = Nem vagy egyedül. Ha arra gondolsz, hogy véget vetsz az életednek, beszélj valakivel
  most: hívd az országod segélyhívó számát, vagy keress ingyenes lelkisegély-vonalat a
  https://findahelpline.com oldalon.

@el Ελληνικά | wiki=el | schrift=greek
hallo = γεια σου; γεια σας; γεια; καλημέρα; καλησπέρα; χαίρετε
info = ποιος είσαι; τι μπορείς να κάνεις; βοήθεια
danke = ευχαριστώ; ευχαριστώ πολύ; σε ευχαριστώ; ευχαριστώ πάρα πολύ
tschuess = αντίο; τα λέμε; καληνύχτα; γεια χαρά
wiegehts = τι κάνεις; πώς είσαι; τι κάνετε; όλα καλά
wetter = καιρός; καιρό; πρόγνωση καιρού; θερμοκρασία; βρέχει
zeit = τι ώρα είναι; τι ώρα; η ώρα
datum = τι ημερομηνία είναι; τι μέρα είναι σήμερα; σημερινή ημερομηνία
heute = σήμερα
morgen = αύριο
wiki = τι είναι {x}; τι είναι η {x}; τι είναι ο {x}; ποιος είναι ο {x}; ποια είναι η {x};
  ποιος ήταν ο {x}; πες μου για {x}
stopp = στην; στο; στη; σε; ο; η; το; τι; πώς; θα; κάνει; σήμερα; αύριο; τώρα; είναι
krise = αυτοκτονία; θέλω να πεθάνω; να σκοτωθώ; να αυτοκτονήσω
A.intro = Γεια σου! Είμαι ο Aquaticy Standard. Μπορώ να σου πω τον καιρό, την ώρα και την
  ημερομηνία, να κάνω υπολογισμούς και να ψάξω στη Βικιπαίδεια.
A.danke = Παρακαλώ!
A.tschuess = Αντίο! Τα λέμε.
A.wiegehts = Είμαι καλά, ευχαριστώ! Πώς μπορώ να βοηθήσω;
A.zeit = Η ώρα είναι {zeit}.
A.datum = Σήμερα είναι {datum}.
A.ort = Για ποιο μέρος θέλεις τον καιρό;
A.nichts = Λυπάμαι, δεν βρήκα τίποτα για «{x}».
A.rueckfall = Λυπάμαι, χωρίς γλωσσικό μοντέλο δεν μπορώ να απαντήσω σε αυτό. Ρώτα με για τον
  καιρό, την ώρα, την ημερομηνία, έναν υπολογισμό ή κάτι από τη Βικιπαίδεια.
A.krise = Δεν είσαι μόνος. Αν σκέφτεσαι να βάλεις τέλος στη ζωή σου, μίλησε με κάποιον τώρα: κάλεσε
  τον αριθμό έκτακτης ανάγκης της χώρας σου ή βρες μια δωρεάν γραμμή βοήθειας στο
  https://findahelpline.com.

@cs Čeština | wiki=cs | schrift=latin
zeichen = ř;ů;ě
hallo = ahoj; dobrý den; dobré ráno; dobrý večer; čau; nazdar
info = kdo jsi; co umíš; co dokážeš; pomoc; pomoz mi
danke = děkuji; díky; děkuju; moc děkuji; mockrát děkuji
tschuess = na shledanou; ahoj zatím; měj se; dobrou noc; zatím
wiegehts = jak se máš; jak se máte; jak se vede; co děláš
wetter = počasí; předpověď počasí; teplota; prší; déšť; pršet
zeit = kolik je hodin; kolik je; jaký je čas
datum = jaké je dnes datum; kolikátého je dnes; jaký je dnes den; dnešní datum
heute = dnes
morgen = zítra
wiki = co je {x}; co je to {x}; kdo je {x}; kdo byl {x}; řekni mi o {x}
stopp = v; ve; na; pro; jaké; jaký; jak; bude; dnes; zítra; teď; je; řekni; pršet; prší
krise = zabít se; chci umřít; sebevražda; vzít si život
A.intro = Ahoj! Jsem Aquaticy Standard. Můžu ti říct počasí, čas a datum, počítat a hledat na
  Wikipedii.
A.danke = Není zač!
A.tschuess = Na shledanou!
A.wiegehts = Mám se dobře, díky! S čím můžu pomoct?
A.zeit = Je {zeit}.
A.datum = Dnes je {datum}.
A.ort = Pro jaké místo mám zjistit počasí?
A.nichts = Promiň, o „{x}“ jsem nic nenašel.
A.rueckfall = Promiň, bez jazykového modelu na to nedokážu odpovědět. Zeptej se mě na počasí,
  čas, datum, výpočet nebo něco z Wikipedie.
A.krise = Nejsi sám. Pokud přemýšlíš o tom, že si vezmeš život, promluv si s někým hned teď:
  zavolej na tísňovou linku ve své zemi nebo najdi bezplatnou linku pomoci na
  https://findahelpline.com.

@sv Svenska | wiki=sv | schrift=latin
zeichen = å
hallo = hej; hejsan; god morgon; god kväll; tjena; hallå
info = vem är du; vad kan du; vad kan du göra; hjälp
danke = tack; tack så mycket; tusen tack; tackar
tschuess = hej då; vi ses; adjö; god natt; ha det bra
wiegehts = hur mår du; hur är det; läget; hur har du det
wetter = väder; vädret; väderprognos; temperatur; regnar; regna; kommer det att regna
zeit = vad är klockan; hur mycket är klockan; klockan
datum = vilket datum är det; vad är det för datum; vilken dag är det; dagens datum
heute = idag
morgen = imorgon
wiki = vad är {x}; vem är {x}; vem var {x}; berätta om {x}
stopp = i; på; för; hur; blir; är; det; idag; imorgon; nu; vad; kommer; att; regna; regnar
krise = ta livet av mig; vill dö; självmord
A.intro = Hej! Jag är Aquaticy Standard. Jag kan berätta om vädret, tiden och datumet, räkna och
  söka på Wikipedia.
A.danke = Varsågod!
A.tschuess = Hej då! Vi ses.
A.wiegehts = Jag mår bra, tack! Hur kan jag hjälpa dig?
A.zeit = Klockan är {zeit}.
A.datum = Idag är det {datum}.
A.ort = För vilken plats vill du veta vädret?
A.nichts = Tyvärr hittade jag inget om ”{x}”.
A.rueckfall = Tyvärr kan jag inte svara på det utan en språkmodell. Fråga mig om vädret, tiden,
  datumet, en uträkning eller något från Wikipedia.
A.krise = Du är inte ensam. Om du tänker på att ta ditt liv, prata med någon nu: ring
  nödnumret i ditt land eller hitta en kostnadsfri stödlinje på https://findahelpline.com.

@az Azərbaycanca | wiki=az | schrift=latin
zeichen = ə
hallo = salam; salam aleykum; sabahınız xeyir; axşamınız xeyir; xoş gördük
info = sən kimsən; siz kimsiniz; nə edə bilərsən; kömək
danke = təşəkkür edirəm; sağ ol; çox sağ ol; təşəkkürlər; çox sağ olun
tschuess = sağ ol görüşənədək; hələlik; görüşərik; gecəniz xeyrə qalsın; xudahafiz
wiegehts = necəsən; necəsiniz; nə var nə yox; yaxşısan
wetter = hava; hava necədir; hava proqnozu; temperatur; yağış
zeit = saat neçədir; indi saat neçədir; vaxt neçədir
datum = bu gün ayın neçəsidir; bugünkü tarix; bu gün hansı gündür
heute = bu gün
morgen = sabah
wiki = {x} nədir; {x} kimdir; {x} haqqında danış
stopp = da; də; necə; nə; bu; gün; sabah; olacaq; indi; necədir
krise = intihar; ölmək istəyirəm; özümü öldür
A.intro = Salam! Mən Aquaticy Standard-am. Sizə havanı, saatı və tarixi deyə, hesablaya və
  Vikipediyada axtara bilərəm.
A.danke = Buyurun!
A.tschuess = Sağ olun! Görüşənədək.
A.wiegehts = Yaxşıyam, təşəkkür edirəm! Sizə necə kömək edə bilərəm?
A.zeit = İndi saat {zeit}.
A.datum = Bu gün {datum}.
A.ort = Hansı yerin havasına baxım?
A.nichts = Bağışlayın, “{x}” haqqında heç nə tapmadım.
A.rueckfall = Bağışlayın, dil modeli olmadan buna cavab verə bilmərəm. Məndən hava, saat, tarix,
  hesablama və ya Vikipediyadan bir şey soruşun.
A.krise = Siz tək deyilsiniz. Əgər həyatınıza son qoymağı düşünürsünüzsə, indi kiminləsə danışın:
  ölkənizin təcili yardım nömrəsinə zəng edin və ya https://findahelpline.com saytında pulsuz
  yardım xətti tapın.

@kk Қазақша | wiki=kk | schrift=cyrillic
zeichen = ә;ғ;қ;ң;ө;ұ;ү;һ;і
hallo = сәлем; сәлеметсіз бе; қайырлы таң; қайырлы кеш; ассалаумағалейкум
info = сен кімсің; сіз кімсіз; не істей аласың; көмек
danke = рахмет; көп рахмет; алғыс
tschuess = сау бол; көріскенше; қайырлы түн; сау болыңыз
wiegehts = қалайсың; қалайсыз; жағдайың қалай; халің қалай
wetter = ауа райы; ауа-райы; температура; жаңбыр
zeit = сағат неше; қазір сағат неше; уақыт қанша
datum = бүгін нешесі; бүгінгі күн; бүгін қай күн
heute = бүгін
morgen = ертең
wiki = {x} деген не; {x} дегеніміз не; {x} кім; {x} туралы айтшы
stopp = да; де; та; те; қандай; қалай; бүгін; ертең; болады; қазір; айтшы
krise = өзімді өлтіргім; өлгім келеді; суицид
A.intro = Сәлем! Мен Aquaticy Standard-пын. Сізге ауа райын, уақытты және күнді айта аламын,
  есептей аламын және Уикипедиядан іздей аламын.
A.danke = Оқасы жоқ!
A.tschuess = Сау болыңыз! Көріскенше.
A.wiegehts = Жақсымын, рахмет! Сізге қалай көмектесе аламын?
A.zeit = Қазір сағат {zeit}.
A.datum = Бүгін {datum}.
A.ort = Қай жердің ауа райын қарайын?
A.nichts = Кешіріңіз, «{x}» туралы ештеңе таппадым.
A.rueckfall = Кешіріңіз, тілдік модельсіз бұған жауап бере алмаймын. Менен ауа райы, уақыт, күн,
  есеп немесе Уикипедиядағы бір нәрсе туралы сұраңыз.
A.krise = Сіз жалғыз емессіз. Егер өміріңізді қиюды ойлап жүрсеңіз, дәл қазір біреумен сөйлесіңіз:
  еліңіздің жедел көмек нөміріне қоңырау шалыңыз немесе https://findahelpline.com сайтынан
  тегін көмек желісін табыңыз.

@be Беларуская | wiki=be | schrift=cyrillic
zeichen = ў;і
hallo = прывітанне; добры дзень; дабрыдзень; вітаю; добрай раніцы; добры вечар
info = хто ты; што ты ўмееш; што ты можаш; дапамога
danke = дзякуй; вялікі дзякуй; дзякую
tschuess = бывай; да пабачэння; дабранач; да сустрэчы
wiegehts = як справы; як ты; як маешся
wetter = надвор'е; прагноз надвор'я; тэмпература; дождж
zeit = колькі часу; каторая гадзіна; які час
datum = якое сёння чысло; якая сёння дата; які сёння дзень
heute = сёння
morgen = заўтра
wiki = што такое {x}; хто такі {x}; хто такая {x}; раскажы пра {x}
stopp = у; ў; на; для; якое; як; будзе; сёння; заўтра; цяпер; скажы
krise = скончыць з сабой; хачу памерці; самагубства
A.intro = Прывітанне! Я Aquaticy Standard. Я магу сказаць надвор'е, час і дату, палічыць і
  пашукаць у Вікіпедыі.
A.danke = Калі ласка!
A.tschuess = Да пабачэння!
A.wiegehts = У мяне ўсё добра, дзякуй! Чым магу дапамагчы?
A.zeit = Цяпер {zeit}.
A.datum = Сёння {datum}.
A.ort = Для якога месца паказаць надвор'е?
A.nichts = Прабачце, я нічога не знайшоў пра «{x}».
A.rueckfall = Прабачце, без моўнай мадэлі я не магу на гэта адказаць. Спытайце пра надвор'е, час,
  дату, падлік ці штосьці з Вікіпедыі.
A.krise = Вы не адны. Калі вы думаеце пра тое, каб скончыць з жыццём, пагаварыце з кімсьці зараз:
  патэлефануйце на мясцовы экстраны нумар або знайдзіце бясплатную лінію дапамогі на
  https://findahelpline.com.

@sr Српски | wiki=sr | schrift=cyrillic
zeichen = ђ;ћ;џ;ј;љ;њ
hallo = здраво; добар дан; добро јутро; добро вече; ћао
info = ко си ти; шта знаш; шта можеш; помоћ
danke = хвала; хвала пуно; хвала вам
tschuess = довиђења; видимо се; лаку ноћ
wiegehts = како си; како сте; шта има
wetter = време; временска прогноза; температура; киша
zeit = колико је сати; које је време
datum = који је данас датум; који је данас дан
heute = данас
morgen = сутра
wiki = шта је {x}; ко је {x}; ко је био {x}
stopp = у; на; за; какво; како; ће; бити; данас; сутра; сада; је
krise = убијем се; желим да умрем; самоубиство
A.intro = Здраво! Ја сам Aquaticy Standard. Могу да ти кажем време, сат и датум, да рачунам и да
  тражим на Википедији.
A.danke = Нема на чему!
A.tschuess = Довиђења! Видимо се.
A.wiegehts = Добро сам, хвала! Како могу да помогнем?
A.zeit = Сада је {zeit}.
A.datum = Данас је {datum}.
A.ort = За које место да проверим време?
A.nichts = Извини, нисам нашао ништа о „{x}”.
A.rueckfall = Извини, без језичког модела не могу на то да одговорим. Питај ме за време, сат,
  датум, рачун или нешто са Википедије.
A.krise = Ниси сам. Ако размишљаш да себи одузмеш живот, разговарај са неким одмах: позови број за
  хитне случајеве у својој земљи или пронађи бесплатну линију помоћи на
  https://findahelpline.com.

@bg Български | wiki=bg | schrift=cyrillic
zeichen = ъ;щ
hallo = здравей; здравейте; добър ден; добро утро; добър вечер; здрасти
info = кой си ти; какво можеш; какво умееш; помощ
danke = благодаря; мерси; много благодаря; благодаря ти
tschuess = довиждане; чао; до скоро; лека нощ; всичко хубаво
wiegehts = как си; как сте; какво правиш; как върви
wetter = времето; прогноза за времето; температура; вали
zeit = колко е часът; колко часа е; колко е часа
datum = коя дата е днес; кой ден е днес; днешна дата
heute = днес
morgen = утре
wiki = какво е {x}; кой е {x}; коя е {x}; кой беше {x}; разкажи за {x}
stopp = в; във; на; за; какво; какво е; как; ще; бъде; днес; утре; сега; кажи
krise = да се самоубия; искам да умра; самоубийство
A.intro = Здравей! Аз съм Aquaticy Standard. Мога да ти кажа времето, часа и датата, да смятам и
  да търся в Уикипедия.
A.danke = Моля!
A.tschuess = Довиждане! До скоро.
A.wiegehts = Добре съм, благодаря! С какво мога да помогна?
A.zeit = Часът е {zeit}.
A.datum = Днес е {datum}.
A.ort = За кое място да проверя времето?
A.nichts = Съжалявам, не намерих нищо за „{x}“.
A.rueckfall = Съжалявам, без езиков модел не мога да отговоря на това. Попитай ме за времето,
  часа, датата, сметка или нещо от Уикипедия.
A.krise = Не си сам. Ако мислиш да сложиш край на живота си, говори с някого сега: обади се на
  номера за спешни случаи в твоята страна или намери безплатна линия за помощ на
  https://findahelpline.com.

@he עברית | wiki=he | schrift=hebrew
hallo = שלום; היי; בוקר טוב; ערב טוב; אהלן
info = מי אתה; מי את; מה אתה יכול לעשות; מה את יכולה לעשות; עזרה
danke = תודה; תודה רבה; תודה לך
tschuess = להתראות; ביי; לילה טוב; נתראה
wiegehts = מה שלומך; מה נשמע; מה המצב; איך אתה
wetter = מזג אוויר; מזג האוויר; תחזית; טמפרטורה; גשם
zeit = מה השעה; כמה השעה; השעה עכשיו
datum = מה התאריך; מה התאריך היום; איזה יום היום; התאריך של היום
heute = היום
morgen = מחר
wiki = מה זה {x}; מה זאת {x}; מי זה {x}; מי זאת {x}; מי היה {x}; ספר לי על {x}
stopp = ב; ל; של; מה; איך; יהיה; היום; מחר; עכשיו; את; ה
krise = להתאבד; רוצה למות; להרוג את עצמי; התאבדות
vorsilben = ב; ל; ו; מ; ה
A.intro = שלום! אני Aquaticy Standard. אני יכול לומר לך את מזג האוויר, השעה והתאריך, לחשב
  ולחפש בוויקיפדיה.
A.danke = בבקשה!
A.tschuess = להתראות!
A.wiegehts = אני בסדר, תודה! איך אפשר לעזור?
A.zeit = השעה עכשיו {zeit}.
A.datum = היום {datum}.
A.ort = לאיזה מקום לבדוק את מזג האוויר?
A.nichts = סליחה, לא מצאתי שום דבר על „{x}”.
A.rueckfall = סליחה, בלי מודל שפה אני לא יכול לענות על זה. שאל אותי על מזג האוויר, השעה,
  התאריך, חישוב או משהו מוויקיפדיה.
A.krise = אתה לא לבד. אם אתה חושב לשים קץ לחייך, דבר עם מישהו עכשיו: התקשר למספר החירום
  במדינה שלך או מצא קו סיוע חינמי בכתובת https://findahelpline.com.

@ceb Cebuano | wiki=ceb | schrift=latin
hallo = maayong buntag; maayong hapon; maayong gabii; kumusta ka diha
info = kinsa ka; unsa imong mahimo; tabang; tabangi ko
danke = salamat kaayo; daghang salamat
tschuess = babay; adios; sa sunod nalang; amping
wiegehts = kumusta naman ka; maayo ra ka; unsa na man
wetter = panahon karon; klima; init; ulan; uwan
zeit = unsa na orasa; pila na ang oras; alas pila na
datum = unsa petsa karon; petsa karon; unsa adlaw karon
heute = karon
morgen = ugma
wiki = unsa ang {x}; kinsa si {x}; isulti bahin sa {x}
stopp = sa; ang; unsa; karon; ugma; ba; man; mahimong
krise = magpakamatay; gusto na ko mamatay
A.intro = Maayong adlaw! Ako si Aquaticy Standard. Masulti nako ang panahon, oras ug petsa,
  makakuwenta ug makapangita sa Wikipedia.
A.danke = Walay sapayan!
A.tschuess = Babay! Amping.
A.wiegehts = Maayo ra ko, salamat! Unsaon nako pagtabang nimo?
A.zeit = Karon kay {zeit}.
A.datum = Karon kay {datum}.
A.ort = Asa nga lugar ang akong tan-awon ang panahon?
A.nichts = Pasayloa, wala koy nakit-an bahin sa “{x}”.
A.rueckfall = Pasayloa, dili nako matubag kana kung walay language model. Pangutana bahin sa
  panahon, oras, petsa, kuwenta o butang sa Wikipedia.
A.krise = Dili ka nag-inusara. Kung naghunahuna ka nga tapuson ang imong kinabuhi, palihug pakig-
  istorya sa usa ka tawo karon: tawag sa emergency number sa imong nasud o pangitaa ang libreng
  helpline sa https://findahelpline.com.

@mg Malagasy | wiki=mg | schrift=latin
hallo = manao ahoana; salama; manahoana; arahaba
info = iza ianao; inona no azonao atao; fanampiana; ampio aho
danke = misaotra; misaotra betsaka; misaotra indrindra
tschuess = veloma; mandra-pihaona; tafandria mandry
wiegehts = manao ahoana ianao; tsara ve ianao; inona no vaovao
wetter = toetrandro; toetr'andro; hafanana; orana
zeit = amin'ny firy izao; firy ora izao; ora firy
datum = faha firy androany; daty androany; inona no andro androany
heute = androany
morgen = rahampitso
wiki = inona no atao hoe {x}; inona ny {x}; iza i {x}; lazao ahy momba ny {x}
stopp = any; amin'ny; ao; ny; ahoana; androany; rahampitso; izao; ho
krise = hamono tena; te ho faty aho
A.intro = Manao ahoana! Aquaticy Standard aho. Afaka milaza aminao ny toetrandro, ny ora sy ny
  daty aho, manao kajy ary mitady ao amin'ny Wikipedia.
A.danke = Tsy misy fisaorana!
A.tschuess = Veloma! Mandra-pihaona.
A.wiegehts = Tsara aho, misaotra! Inona no azoko anampiana anao?
A.zeit = Amin'izao dia {zeit}.
A.datum = Androany dia {datum}.
A.ort = Ny toetrandro any amin'ny toerana inona no hojereko?
A.nichts = Miala tsiny, tsy nahita na inona na inona momba ny “{x}” aho.
A.rueckfall = Miala tsiny, tsy afaka mamaly izany aho raha tsy misy modely fiteny. Anontanio
  momba ny toetrandro, ny ora, ny daty, kajy na zavatra avy amin'ny Wikipedia aho.
A.krise = Tsy irery ianao. Raha mieritreritra ny hamarana ny ainao ianao, mba miresaha amin'olona
  izao: antsoy ny laharana vonjy maika eto amin'ny firenenao na mitadiava tolotra fanampiana
  maimaim-poana ao amin'ny https://findahelpline.com.

@rw Ikinyarwanda | wiki=rw | schrift=latin
hallo = muraho; mwaramutse; mwiriwe; bite
info = uri nde; ushobora gukora iki; ubufasha; mfasha
danke = murakoze; urakoze; murakoze cyane
tschuess = murabeho; turongera; muramuke; ijoro ryiza
wiegehts = amakuru; amakuru yawe; umeze ute; muraho neza
wetter = iteganyagihe; ikirere; ubushyuhe; imvura
zeit = ni saa ngahe; ni isaha zingahe; isaha
datum = uyu munsi ni itariki zingahe; itariki y'uyu munsi; uyu munsi ni uwuhe munsi
heute = uyu munsi
morgen = ejo
wiki = ni iki {x}; {x} ni iki; {x} ni nde; mbwira kuri {x}
stopp = i; mu; kuri; ute; uyu; munsi; ejo; ni; ubu
krise = kwiyahura; ndashaka gupfa
A.intro = Muraho! Ndi Aquaticy Standard. Nshobora kukubwira iteganyagihe, isaha n'itariki,
  kubara no gushakisha kuri Wikipedia.
A.danke = Nta kibazo!
A.tschuess = Murabeho!
A.wiegehts = Ndi mwiza, urakoze! Nagufasha iki?
A.zeit = Ubu ni {zeit}.
A.datum = Uyu munsi ni {datum}.
A.ort = Ndebe iteganyagihe ry'ahantu he?
A.nichts = Mbabarira, nta kintu nabonye kuri “{x}”.
A.rueckfall = Mbabarira, sinshobora gusubiza ibyo nta modeli y'ururimi. Mbaza ku iteganyagihe,
  isaha, itariki, imibare cyangwa ikintu cyo kuri Wikipedia.
A.krise = Ntabwo uri wenyine. Niba utekereza kwiyahura, nyamuneka vugana n'umuntu ubu: hamagara
  nimero y'ubutabazi bwihuse mu gihugu cyawe cyangwa ushake umurongo w'ubufasha w'ubuntu kuri
  https://findahelpline.com.

@tw Twi | wiki=tw | schrift=latin
zeichen = ɛ;ɔ
hallo = maakye; maaha; maadwo; agoo; ɛte sɛn
info = wo ne hwan; dɛn na wobɛtumi ayɛ; mmoa; boa me
danke = medaase; meda wo ase; medaase paa
tschuess = nante yie; yɛbɛhyia; da yie; bye bye
wiegehts = wo ho te sɛn; ɛte sɛn; wo ho yɛ
wetter = wim tebea; ewiem; ahohuru; nsuo tɔ
zeit = abɔ sɛn; dɔn sɛn na abɔ; mprempren abɔ sɛn
datum = ɛnnɛ yɛ da bɛn; ɛnnɛ da; ɛnnɛ yɛ dabɛn
heute = ɛnnɛ
morgen = ɔkyena
wiki = dɛn ne {x}; hwan ne {x}; ka {x} ho asɛm kyerɛ me
stopp = wɔ; mu; sɛn; ɛnnɛ; ɔkyena; bɛ; yɛ; mprempren
krise = kum me ho; mepɛ sɛ mewu
A.intro = Akwaaba! Me ne Aquaticy Standard. Metumi aka wim tebea, dɔn ne da kyerɛ wo, abu akonta
  na mahwehwɛ nneɛma wɔ Wikipedia so.
A.danke = Ɛnyɛ hwee!
A.tschuess = Nante yie! Yɛbɛhyia.
A.wiegehts = Me ho yɛ, medaase! Ɛdeɛn na mɛtumi aboa wo?
A.zeit = Mprempren abɔ {zeit}.
A.datum = Ɛnnɛ yɛ {datum}.
A.ort = Beae bɛn wim tebea na menhwɛ?
A.nichts = Kafra, manhunu biribiara fa “{x}” ho.
A.rueckfall = Kafra, mentumi mmua eyi a kasa model nni hɔ. Bisa me wim tebea, dɔn, da, akontaa
  anaa biribi a ɛwɔ Wikipedia so.
A.krise = Ɛnyɛ wo nko ara. Sɛ woredwene sɛ wobɛkum wo ho a, mesrɛ wo kasa kyerɛ obi seesei: frɛ
  wo man no ahotɔ nɔma anaa hwehwɛ mmoa a wontua hwee wɔ https://findahelpline.com.

@ny Chichewa | wiki=ny | schrift=latin
hallo = moni; muli bwanji; mwadzuka bwanji; mwaswera bwanji
info = ndiwe ndani; mungachite chiyani; thandizo; ndithandizeni
danke = zikomo; zikomo kwambiri; tawonga
tschuess = tsalani bwino; pitani bwino; tionana; gonani bwino
wiegehts = muli bwanji; uli bwanji; ndili bwino kaya inu
wetter = nyengo; mvula; kutentha
zeit = nthawi yanji; ndi nthawi yanji; ndi koloko bwanji
datum = lero ndi tsiku lanji; deti la lero; lero ndi tsiku liti
heute = lero
morgen = mawa
wiki = kodi {x} ndi chiyani; {x} ndi chiyani; {x} ndi ndani; ndiuzeni za {x}
stopp = ku; ya; mu; bwanji; lero; mawa; ndi; tsopano; kodi
krise = kudzipha; ndikufuna kufa
A.intro = Moni! Ndine Aquaticy Standard. Ndingakuuzeni nyengo, nthawi ndi deti, kuwerengera
  ndikusaka pa Wikipedia.
A.danke = Zikomo kwa inu!
A.tschuess = Tsalani bwino!
A.wiegehts = Ndili bwino, zikomo! Ndingakuthandizeni bwanji?
A.zeit = Tsopano ndi {zeit}.
A.datum = Lero ndi {datum}.
A.ort = Ndiyang'ane nyengo ya malo ati?
A.nichts = Pepani, sindinapeze kanthu za “{x}”.
A.rueckfall = Pepani, sindingayankhe zimenezo popanda chitsanzo cha chilankhulo. Ndifunseni za
  nyengo, nthawi, deti, kuwerengera kapena chinthu cha pa Wikipedia.
A.krise = Simuli nokha. Ngati mukuganiza zodzipha, chonde lankhulani ndi munthu tsopano: imbani
  nambala yadzidzidzi ya dziko lanu kapena pezani thandizo laulere pa https://findahelpline.com.

@sn chiShona | wiki=sn | schrift=latin
hallo = mhoro; mhoroi; mangwanani; masikati; manheru
info = ndiwe ani; unogona kuitei; rubatsiro; ndibatsire
danke = ndatenda; ndatenda zvikuru; maita basa; tatenda
tschuess = sara zvakanaka; famba zvakanaka; tichaonana; murare zvakanaka
wiegehts = makadii; wakadini; mamuka sei; maswera sei
wetter = mamiriro ekunze; kunze; kupisa; mvura
zeit = inguva yei; ndeipi nguva; nguva ngani
datum = nhasi idhiti ripi; zuva ranhasi; nhasi izuva ripi
heute = nhasi
morgen = mangwana
wiki = chii {x}; {x} chii; ndiani {x}; ndiudze nezve {x}
stopp = mu; ku; pa; sei; nhasi; mangwana; ichava; zvino; ekunze; mamiriro
krise = kuzviuraya; ndinoda kufa
A.intro = Mhoro! Ndini Aquaticy Standard. Ndinogona kukuudza mamiriro ekunze, nguva nezuva,
  kuverenga uye kutsvaga paWikipedia.
A.danke = Hapana basa!
A.tschuess = Sara zvakanaka! Tichaonana.
A.wiegehts = Ndiri mushe, ndatenda! Ndingakubatsira nei?
A.zeit = Iye zvino inguva {zeit}.
A.datum = Nhasi i{datum}.
A.ort = Nditarise mamiriro ekunze enzvimbo ipi?
A.nichts = Ndine urombo, handina kuwana chinhu nezve “{x}”.
A.rueckfall = Ndine urombo, handikwanise kupindura izvozvo pasina modhi yemutauro. Ndibvunze
  nezve mamiriro ekunze, nguva, zuva, kuverenga kana chimwe chinhu cheWikipedia.
A.krise = Hausi woga. Kana uchifunga kuzviuraya, ndapota taura nemumwe munhu iye zvino: fonera
  nhamba yechimbichimbi yenyika yako kana uwane rubatsiro rwemahara pa https://findahelpline.com.

@qu Runasimi | wiki=qu | schrift=latin
hallo = allillanchu; rimaykullayki; napaykullayki; imaynalla
info = pitaq kanki; imatataq ruwayta atinki; yanapay; yanapawai
danke = sulpayki; añay; yusulpayki; sulpayki ancha
tschuess = tupananchiskama; ratukama; paqarinkama
wiegehts = imaynallam kachkanki; allinllachu; imaynalla kachkanki
wetter = pacha; pacha imayna; para; ruphay
zeit = hayka horam; hayka horataq; kunan hayka horam
datum = kunan hayka punchawtaq; kunan punchaw; ima punchawtaq kunan
heute = kunan
morgen = paqarin
wiki = imataq {x}; pitaq {x}; {x} ima; willaway {x}manta
stopp = pi; manta; imayna; kunan; paqarin; kanqa; taq
krise = wañuyta munani; kikiyta wañuchiy
A.intro = Allillanchu! Ñuqa kani Aquaticy Standard. Willayta atini pachamanta, horamanta,
  punchawmantapas, yupayta, Wikipediapi maskaytapas.
A.danke = Mana imamanta!
A.tschuess = Tupananchiskama!
A.wiegehts = Allillanmi kachkani, sulpayki! Imapitaq yanapayki?
A.zeit = Kunanqa {zeit}.
A.datum = Kunan punchawqa {datum}.
A.ort = Mayqin llaqtapa pachantataq qhawasaq?
A.nichts = Pampachaway, manam imatapas tarirqanichu “{x}”manta.
A.rueckfall = Pampachaway, mana simi modelowan kaspaqa manam kutichiyta atinichu. Tapuway
  pachamanta, horamanta, punchawmanta, yupaymanta utaq Wikipediamanta.
A.krise = Manam sapallaykichu kanki. Kawsayniykita tukuchiyta yuyaykuspaqa, kunanpacha pimanpas
  rimay: llaqtaykipa emergencia yupayninman waqyay utaq mana qullqiyuq yanapayta maskay
  https://findahelpline.com nisqapi.

@ht Kreyòl ayisyen | wiki=ht | schrift=latin
hallo = bonjou; bonswa; alo; sak pase
info = kiyès ou ye; kisa ou ka fè; èd; ede m
danke = mèsi; mèsi anpil; mèsi bokou
tschuess = orevwa; na wè; bòn nwit; pita
wiegehts = kijan ou ye; sak pase; ki jan ou ye; ou byen
wetter = tan an; meteyo; lapli; chalè
zeit = ki lè li ye; kilè li ye; ki lè li fè
datum = ki dat jodi a; dat jodi a; ki jou jodi a
heute = jodi a
morgen = demen
wiki = kisa ki {x}; kisa {x} ye; kiyès {x} ye; pale m de {x}
stopp = nan; a; pou; ki; jan; jodi; demen; pral; ye; kounye a; tan
krise = touye tèt mwen; mwen vle mouri; swisid
A.intro = Bonjou! Mwen se Aquaticy Standard. Mwen ka di w tan an, lè a ak dat la, fè kalkil epi
  chèche sou Wikipedya.
A.danke = Pa gen pwoblèm!
A.tschuess = Orevwa! Na wè.
A.wiegehts = Mwen byen, mèsi! Kijan mwen ka ede w?
A.zeit = Li {zeit}.
A.datum = Jodi a se {datum}.
A.ort = Pou ki kote ou vle konnen tan an?
A.nichts = Padon, mwen pa jwenn anyen sou “{x}”.
A.rueckfall = Padon, san yon modèl lang mwen pa ka reponn sa. Mande m pou tan an, lè a, dat la,
  yon kalkil oswa yon bagay sou Wikipedya.
A.krise = Ou pa poukont ou. Si w ap panse pou w mete fen ak lavi w, tanpri pale ak yon moun kounye
  a: rele nimewo ijans peyi w la oswa jwenn yon liy èd gratis sou https://findahelpline.com.

@da Dansk | wiki=da | schrift=latin
zeichen = ø;æ
hallo = hej; hejsa; godmorgen; god morgen; godaften; goddag; halløj
info = hvem er du; hvad kan du; hvad kan du gøre; hjælp
danke = tak; mange tak; tusind tak; tak skal du have
tschuess = farvel; vi ses; god nat; hej hej; hav det godt
wiegehts = hvordan har du det; hvordan går det; går det godt
wetter = vejret; vejrudsigt; temperatur; regner; vejr
zeit = hvad er klokken; hvor mange er klokken; klokken
datum = hvilken dato er det; hvad er datoen; hvilken dag er det; dagens dato
heute = i dag
morgen = i morgen
wiki = hvad er {x}; hvem er {x}; hvem var {x}; fortæl om {x}
stopp = i; på; for; hvordan; bliver; er; det; dag; morgen; nu; hvad
krise = tage mit eget liv; vil dø; selvmord
A.intro = Hej! Jeg er Aquaticy Standard. Jeg kan fortælle dig vejret, klokken og datoen, regne og
  søge på Wikipedia.
A.danke = Selv tak!
A.tschuess = Farvel! Vi ses.
A.wiegehts = Jeg har det godt, tak! Hvordan kan jeg hjælpe?
A.zeit = Klokken er {zeit}.
A.datum = I dag er det {datum}.
A.ort = For hvilket sted vil du kende vejret?
A.nichts = Beklager, jeg fandt intet om »{x}«.
A.rueckfall = Beklager, uden en sprogmodel kan jeg ikke svare på det. Spørg mig om vejret,
  klokken, datoen, en udregning eller noget fra Wikipedia.
A.krise = Du er ikke alene. Hvis du tænker på at tage dit eget liv, så tal med nogen nu: ring til
  nødnummeret i dit land eller find en gratis hjælpelinje på https://findahelpline.com.

@fi Suomi | wiki=fi | schrift=latin
hallo = hei; moi; terve; huomenta; hyvää päivää; hyvää iltaa; moikka
info = kuka olet; mitä osaat; mitä voit tehdä; apua; auta
danke = kiitos; kiitos paljon; kiitti; kiitoksia
tschuess = näkemiin; hei hei; moikka moi; hyvää yötä; nähdään
wiegehts = mitä kuuluu; miten menee; kuinka voit
wetter = sää; sääennuste; millainen sää; lämpötila; sataa
zeit = paljonko kello on; mitä kello on; kello
datum = mikä päivämäärä on; monesko päivä tänään on; mikä päivä tänään on; päivämäärä
heute = tänään
morgen = huomenna
wiki = mikä on {x}; kuka on {x}; kuka oli {x}; kerro {x}
stopp = millainen; on; sää; tänään; huomenna; nyt; mikä; miten
endungen = ssa; ssä; lla; llä
krise = tappaa itseni; haluan kuolla; itsemurha
A.intro = Hei! Olen Aquaticy Standard. Voin kertoa sään, kellonajan ja päivämäärän, laskea ja
  hakea Wikipediasta.
A.danke = Ole hyvä!
A.tschuess = Näkemiin!
A.wiegehts = Hyvää kuuluu, kiitos! Miten voin auttaa?
A.zeit = Kello on {zeit}.
A.datum = Tänään on {datum}.
A.ort = Minkä paikan sään haluat tietää?
A.nichts = Valitettavasti en löytänyt mitään aiheesta ”{x}”.
A.rueckfall = Valitettavasti en voi vastata tuohon ilman kielimallia. Kysy minulta säätä,
  kellonaikaa, päivämäärää, laskua tai jotain Wikipediasta.
A.krise = Et ole yksin. Jos ajattelet elämäsi päättämistä, puhu jonkun kanssa nyt: soita maasi
  hätänumeroon tai etsi maksuton auttava puhelin osoitteesta https://findahelpline.com.

@no Norsk | wiki=no | schrift=latin
zeichen = ø;æ
hallo = hei; hallo; god morgen; god kveld; heisann; morn
info = hvem er du; hva kan du; hva kan du gjøre; hjelp
danke = takk; tusen takk; takk skal du ha; mange takk
tschuess = ha det; ha det bra; vi ses; god natt; adjø
wiegehts = hvordan har du det; hvordan går det; står til
wetter = været; værmelding; vær; temperatur; regner
zeit = hva er klokka; hvor mye er klokka; hva er klokken; klokka
datum = hvilken dato er det; hva er datoen; hvilken dag er det; dagens dato
heute = i dag
morgen = i morgen
wiki = hva er {x}; hvem er {x}; hvem var {x}; fortell om {x}
stopp = i; på; for; hvordan; blir; er; det; dag; morgen; nå; hva
krise = ta livet mitt; vil dø; selvmord
A.intro = Hei! Jeg er Aquaticy Standard. Jeg kan fortelle deg været, klokka og datoen, regne og
  søke på Wikipedia.
A.danke = Bare hyggelig!
A.tschuess = Ha det bra! Vi ses.
A.wiegehts = Jeg har det bra, takk! Hvordan kan jeg hjelpe?
A.zeit = Klokka er {zeit}.
A.datum = I dag er det {datum}.
A.ort = For hvilket sted vil du vite været?
A.nichts = Beklager, jeg fant ingenting om «{x}».
A.rueckfall = Beklager, uten en språkmodell kan jeg ikke svare på det. Spør meg om været, klokka,
  datoen, en utregning eller noe fra Wikipedia.
A.krise = Du er ikke alene. Hvis du tenker på å ta livet ditt, snakk med noen nå: ring nødnummeret
  i landet ditt eller finn en gratis hjelpetelefon på https://findahelpline.com.

@sk Slovenčina | wiki=sk | schrift=latin
zeichen = ľ;ĺ;ŕ;ô
hallo = ahoj; dobrý deň; dobré ráno; dobrý večer; čau; zdravím
info = kto si; čo vieš; čo dokážeš; pomoc; pomôž mi
danke = ďakujem; vďaka; ďakujem pekne; ďakujem veľmi pekne
tschuess = dovidenia; maj sa; dobrú noc; zatiaľ; uvidíme sa
wiegehts = ako sa máš; ako sa máte; ako sa darí; čo robíš
wetter = počasie; predpoveď počasia; teplota; prší; dážď
zeit = koľko je hodín; aký je čas; koľko je
datum = aký je dnes dátum; koľkého je dnes; aký je dnes deň; dnešný dátum
heute = dnes
morgen = zajtra
wiki = čo je {x}; čo je to {x}; kto je {x}; kto bol {x}; povedz mi o {x}
stopp = v; vo; na; pre; aké; aký; ako; bude; dnes; zajtra; teraz; je; povedz
krise = zabiť sa; chcem zomrieť; samovražda; vziať si život
A.intro = Ahoj! Som Aquaticy Standard. Môžem ti povedať počasie, čas a dátum, počítať a hľadať na
  Wikipédii.
A.danke = Nie je za čo!
A.tschuess = Dovidenia!
A.wiegehts = Mám sa dobre, vďaka! S čím ti môžem pomôcť?
A.zeit = Je {zeit}.
A.datum = Dnes je {datum}.
A.ort = Pre aké miesto mám zistiť počasie?
A.nichts = Prepáč, o „{x}“ som nič nenašiel.
A.rueckfall = Prepáč, bez jazykového modelu na to neviem odpovedať. Opýtaj sa ma na počasie, čas,
  dátum, výpočet alebo niečo z Wikipédie.
A.krise = Nie si sám. Ak premýšľaš o tom, že si vezmeš život, porozprávaj sa s niekým hneď teraz:
  zavolaj na tiesňovú linku vo svojej krajine alebo nájdi bezplatnú linku pomoci na
  https://findahelpline.com.

@hr Hrvatski | wiki=hr | schrift=latin
hallo = bok; dobar dan; dobro jutro; dobra večer; pozdrav; zdravo
info = tko si ti; što znaš; što možeš; pomoć; pomozi mi
danke = hvala; hvala lijepa; puno hvala; hvala ti
tschuess = doviđenja; vidimo se; laku noć; bok bok; zbogom
wiegehts = kako si; kako ste; što ima; kako ide
wetter = vrijeme; vremenska prognoza; temperatura; kiša; pada kiša
zeit = koliko je sati; koje je vrijeme; koliko je sad sati
datum = koji je danas datum; koji je danas dan; današnji datum
heute = danas
morgen = sutra
wiki = što je {x}; tko je {x}; tko je bio {x}; reci mi o {x}
stopp = u; na; za; kakvo; kako; će; biti; danas; sutra; sada; je; reci
krise = ubiti se; želim umrijeti; samoubojstvo
A.intro = Bok! Ja sam Aquaticy Standard. Mogu ti reći vrijeme, sat i datum, računati i tražiti na
  Wikipediji.
A.danke = Nema na čemu!
A.tschuess = Doviđenja! Vidimo se.
A.wiegehts = Dobro sam, hvala! Kako mogu pomoći?
A.zeit = Sada je {zeit}.
A.datum = Danas je {datum}.
A.ort = Za koje mjesto da provjerim vrijeme?
A.nichts = Žao mi je, nisam našao ništa o „{x}”.
A.rueckfall = Žao mi je, bez jezičnog modela ne mogu na to odgovoriti. Pitaj me za vrijeme, sat,
  datum, izračun ili nešto s Wikipedije.
A.krise = Nisi sam. Ako razmišljaš o tome da si oduzmeš život, razgovaraj s nekim odmah: nazovi broj
  za hitne slučajeve u svojoj zemlji ili pronađi besplatnu liniju pomoći na
  https://findahelpline.com.

@bs Bosanski | wiki=bs | schrift=latin
hallo = zdravo; dobar dan; dobro jutro; ćao; selam
info = ko si ti; šta znaš; šta možeš; pomoć
danke = hvala; hvala lijepo; puno hvala; hvala puno; fala
tschuess = doviđenja; vidimo se; laku noć; zbogom
wiegehts = kako si; kako ste; šta ima; kako je
wetter = vrijeme; kakvo je vreme; vremenska prognoza; temperatura; kiša
zeit = koliko je sati; koliko je sahat; koje je vrijeme
datum = koji je danas datum; koji je danas dan; današnji datum
heute = danas
morgen = sutra
wiki = šta je {x}; ko je {x}; ko je bio {x}; reci mi o {x}
stopp = u; na; za; kakvo; kako; će; biti; danas; sutra; sada; je
krise = ubiti se; ubijem se; želim umrijeti; želim da umrem; samoubistvo
A.intro = Zdravo! Ja sam Aquaticy Standard. Mogu ti reći vrijeme, sat i datum, računati i tražiti
  na Wikipediji.
A.danke = Nema na čemu!
A.tschuess = Doviđenja!
A.wiegehts = Dobro sam, hvala! Kako mogu pomoći?
A.zeit = Sada je {zeit}.
A.datum = Danas je {datum}.
A.ort = Za koje mjesto da provjerim vrijeme?
A.nichts = Izvini, nisam našao ništa o „{x}”.
A.rueckfall = Izvini, bez jezičkog modela ne mogu na to odgovoriti. Pitaj me za vrijeme, sat,
  datum, račun ili nešto s Wikipedije.
A.krise = Nisi sam. Ako razmišljaš da sebi oduzmeš život, razgovaraj s nekim odmah: pozovi broj za
  hitne slučajeve u svojoj zemlji ili pronađi besplatnu liniju pomoći na
  https://findahelpline.com.

@ug ئۇيغۇرچە | wiki=ug | schrift=arabic
zeichen = ۇ;ۆ;ۈ;ې;ئ
hallo = ياخشىمۇسىز; ئەسسالامۇ ئەلەيكۇم; سالام; خەيرلىك ئەتىگەن
info = سىز كىم; نېمە قىلالايسىز; ياردەم
danke = رەھمەت; كۆپ رەھمەت; تەشەككۈر
tschuess = خەير; خەير خوش; كۆرۈشكۈچە; خاتىرجەم ياتىڭ
wiegehts = ئەھۋالىڭىز قانداق; قانداق ئەھۋالىڭىز; ياخشىمۇ
wetter = ھاۋا رايى; ھاۋا; تېمپېراتۇرا; يامغۇر
zeit = سائەت قانچە بولدى; سائەت قانچە; ھازىر سائەت قانچە
datum = بۈگۈن قانچىنچى; بۈگۈنكى چېسلا; بۈگۈن قايسى كۈن
heute = بۈگۈن
morgen = ئەتە
wiki = {x} دېگەن نېمە; {x} نېمە; {x} كىم
stopp = دا; دىكى; قانداق; نېمە; بۈگۈن; ئەتە; بولىدۇ; ھازىر
krise = ئۆزۈمنى ئۆلتۈرۈش; ئۆلگۈم كېلىدۇ
A.intro = ياخشىمۇسىز! مەن Aquaticy Standard. سىزگە ھاۋا رايى، ۋاقىت ۋە چېسلانى ئېيتىپ بېرەلەيمەن،
  ھېسابلاپ بېرەلەيمەن ۋە ۋىكىپېدىيەدىن ئىزدەپ بېرەلەيمەن.
A.danke = ئەرزىمەيدۇ!
A.tschuess = خەير خوش!
A.wiegehts = ياخشى، رەھمەت! سىزگە قانداق ياردەم قىلالايمەن؟
A.zeit = ھازىر سائەت {zeit}.
A.datum = بۈگۈن {datum}.
A.ort = قايسى جاينىڭ ھاۋا رايىنى كۆرەي؟
A.nichts = كەچۈرۈڭ، «{x}» ھەققىدە ھېچنېمە تاپالمىدىم.
A.rueckfall = كەچۈرۈڭ، تىل مودېلىسىز بۇنىڭغا جاۋاب بېرەلمەيمەن. مەندىن ھاۋا رايى، ۋاقىت، چېسلا،
  ھېسابلاش ياكى ۋىكىپېدىيەدىكى بىرەر نەرسە ھەققىدە سوراڭ.
A.krise = سىز يالغۇز ئەمەس. ئەگەر ھاياتىڭىزنى ئاخىرلاشتۇرۇشنى ئويلاۋاتقان بولسىڭىز، ھازىرلا بىرەرسى
  بىلەن سۆزلىشىڭ: دۆلىتىڭىزنىڭ جىددىي قۇتقۇزۇش نومۇرىغا تېلېفون قىلىڭ ياكى
  https://findahelpline.com دىن ھەقسىز ياردەم لىنىيەسىنى تېپىڭ.

@ku Kurmancî | wiki=ku | schrift=latin
zeichen = ê;î;û
hallo = silav; rojbaş; êvarbaş; merheba; slav
info = tu kî yî; tu dikarî çi bikî; alîkarî; alîkariya min bike
danke = spas; gelek spas; zor spas; sipas
tschuess = bi xatirê te; xatirê te; şev baş; heta carek din
wiegehts = tu çawa yî; çawa yî; baş î; çi heye çi tune
wetter = hewa; hewa çawa; hewa çawa ye; rewşa hewayê; germahî; baran
zeit = saet çend e; niha saet çend e; dem çi ye
datum = îro çend e; dîroka îro; îro kîjan roj e
heute = îro
morgen = sibê
wiki = {x} çi ye; {x} kî ye; li ser {x} bibêje
stopp = li; di; de; ji; çawa; çi; e; dê; îro; sibê; niha; hewaya
krise = xwe bikujim; dixwazim bimirim; xwekuştin
A.intro = Silav! Ez Aquaticy Standard im. Ez dikarim hewa, saet û dîrokê ji te re bibêjim,
  hesab bikim û li Wîkîpediyayê bigerim.
A.danke = Ser çavan!
A.tschuess = Bi xatirê te!
A.wiegehts = Ez baş im, spas! Ez çawa dikarim alîkariya te bikim?
A.zeit = Niha saet {zeit} e.
A.datum = Îro {datum} e.
A.ort = Ez hewaya kîjan derê binêrim?
A.nichts = Bibore, min tiştek li ser “{x}” nedît.
A.rueckfall = Bibore, bê modela zimanî ez nikarim bersiva vê bidim. Ji min li ser hewa, saet,
  dîrok, hesab an tiştekî ji Wîkîpediyayê bipirse.
A.krise = Tu ne tenê yî. Heke tu difikirî ku dawiyê li jiyana xwe bînî, ji kerema xwe niha bi
  kesekî re biaxive: li hejmara acîl a welatê xwe bigere an jî li https://findahelpline.com xetek
  alîkariyê ya belaş bibîne.

@ckb کوردی | wiki=ckb | schrift=arabic
zeichen = ڵ;ڕ;ێ
hallo = سڵاو; بەیانیت باش; ئێوارەت باش; ڕۆژباش
info = تۆ کێیت; چی دەتوانیت بکەیت; یارمەتی
danke = سوپاس; زۆر سوپاس; دەستت خۆش
tschuess = خوات لەگەڵ; خواحافیز; شەو باش; دەتبینمەوە
wiegehts = چۆنی; باشی; چۆنیت; حاڵت چۆنە
wetter = کەشوهەوا; کەش و هەوا; پلەی گەرما; باران
zeit = کاتژمێر چەندە; سەعات چەندە; ئێستا کاتژمێر چەندە
datum = ئەمڕۆ چەندە; بەرواری ئەمڕۆ; ئەمڕۆ چ ڕۆژێکە
heute = ئەمڕۆ
morgen = سبەی
wiki = {x} چییە; {x} کێیە; دەربارەی {x} بڵێ
stopp = لە; دا; ی; چۆن; چییە; دەبێت; ئەمڕۆ; سبەی; ئێستا; بڵێ
krise = خۆکوشتن; دەمەوێت بمرم; خۆم بکوژم
A.intro = سڵاو! من Aquaticy Standard م. دەتوانم کەشوهەوا، کات و بەروارت پێ بڵێم، ژمێریاری بکەم
  و لە ویکیپیدیا بگەڕێم.
A.danke = شایەنی نییە!
A.tschuess = خوات لەگەڵ!
A.wiegehts = باشم، سوپاس! چۆن یارمەتیت بدەم؟
A.zeit = ئێستا کاتژمێر {zeit}ە.
A.datum = ئەمڕۆ {datum}ە.
A.ort = کەشوهەوای کام شوێن ببینم؟
A.nichts = ببورە، هیچم دەربارەی «{x}» نەدۆزییەوە.
A.rueckfall = ببورە، بەبێ مۆدێلی زمان ناتوانم وەڵامی ئەمە بدەمەوە. دەربارەی کەشوهەوا، کات،
  بەروار، ژمێریاری یان شتێک لە ویکیپیدیا بپرسە.
A.krise = تۆ تەنها نیت. ئەگەر بیر لە کۆتاییهێنان بە ژیانت دەکەیتەوە، تکایە ئێستا لەگەڵ کەسێک
  قسە بکە: پەیوەندی بە ژمارەی فریاکەوتنی وڵاتەکەتەوە بکە یان لە https://findahelpline.com
  هێڵێکی یارمەتی بێبەرامبەر بدۆزەرەوە.

@hy Հայերեն | wiki=hy | schrift=armenian
hallo = բարև; բարեւ; բարև ձեզ; բարի լույս; բարի երեկո; ողջույն
info = ով ես դու; ով եք դուք; ինչ կարող ես անել; օգնություն
danke = շնորհակալություն; մերսի; շատ շնորհակալ եմ; շնորհակալ եմ
tschuess = ցտեսություն; հաջող; բարի գիշեր; կհանդիպենք
wiegehts = ինչպես ես; ոնց ես; ինչպես եք; ինչ կա
wetter = եղանակ; եղանակը; ջերմաստիճան; անձրև
zeit = ժամը քանիսն է; ինչ ժամ է; ժամը քանիսն
datum = այսօր ամսի քանիսն է; այսօրվա ամսաթիվը; այսօր ինչ օր է
heute = այսօր
morgen = վաղը
wiki = ինչ է {x}; ով է {x}; {x} ինչ է; պատմիր {x} մասին
stopp = ում; մեջ; ինչպիսին; ինչպես; է; կլինի; այսօր; վաղը; հիմա; ասա
krise = ինքնասպանություն; ուզում եմ մեռնել; ինձ սպանել
A.intro = Բարև! Ես Aquaticy Standard-ն եմ։ Կարող եմ ասել եղանակը, ժամը և ամսաթիվը, հաշվել և
  որոնել Վիքիպեդիայում։
A.danke = Խնդրեմ!
A.tschuess = Ցտեսություն!
A.wiegehts = Լավ եմ, շնորհակալություն։ Ինչով կարող եմ օգնել։
A.zeit = Ժամը {zeit} է։
A.datum = Այսօր {datum} է։
A.ort = Ո՞ր վայրի եղանակը նայեմ։
A.nichts = Ներողություն, «{x}»-ի մասին ոչինչ չգտա։
A.rueckfall = Ներողություն, առանց լեզվական մոդելի չեմ կարող պատասխանել դրան։ Հարցրեք եղանակի,
  ժամի, ամսաթվի, հաշվարկի կամ Վիքիպեդիայից ինչ-որ բանի մասին։
A.krise = Դուք մենակ չեք։ Եթե մտածում եք ձեր կյանքին վերջ տալու մասին, հիմա խոսեք որևէ մեկի հետ՝
  զանգեք ձեր երկրի արտակարգ իրավիճակների համարին կամ գտեք անվճար օգնության գիծ
  https://findahelpline.com կայքում։

@ka ქართული | wiki=ka | schrift=georgian
hallo = გამარჯობა; სალამი; დილა მშვიდობისა; საღამო მშვიდობისა
info = ვინ ხარ; რა შეგიძლია; რისი გაკეთება შეგიძლია; დახმარება
danke = მადლობა; დიდი მადლობა; გმადლობთ; მერსი
tschuess = ნახვამდის; კარგად; ღამე მშვიდობისა; შეხვედრამდე
wiegehts = როგორ ხარ; როგორ ბრძანდებით; რა ხდება; კარგად ხარ
wetter = ამინდი; ამინდის პროგნოზი; ტემპერატურა; წვიმა
zeit = რომელი საათია; რა დროა; ახლა რომელი საათია
datum = დღეს რა რიცხვია; დღევანდელი თარიღი; დღეს რა დღეა
heute = დღეს
morgen = ხვალ
wiki = რა არის {x}; ვინ არის {x}; {x} რა არის; მომიყევი {x} შესახებ
stopp = ში; ზე; როგორი; როგორ; იქნება; დღეს; ხვალ; ახლა; არის; მითხარი
krise = თვითმკვლელობა; მინდა მოვკვდე; თავის მოკვლა
A.intro = გამარჯობა! მე ვარ Aquaticy Standard. შემიძლია გითხრა ამინდი, დრო და თარიღი, გამოვთვალო
  და მოვძებნო ვიკიპედიაში.
A.danke = არაფრის!
A.tschuess = ნახვამდის!
A.wiegehts = კარგად ვარ, მადლობა! რით შემიძლია დაგეხმარო?
A.zeit = ახლა არის {zeit}.
A.datum = დღეს არის {datum}.
A.ort = რომელი ადგილის ამინდი ვნახო?
A.nichts = ბოდიში, „{x}“-ზე ვერაფერი ვიპოვე.
A.rueckfall = ბოდიში, ენობრივი მოდელის გარეშე ამაზე ვერ გიპასუხებ. მკითხე ამინდზე, დროზე,
  თარიღზე, გამოთვლაზე ან რამეზე ვიკიპედიიდან.
A.krise = შენ მარტო არ ხარ. თუ სიცოცხლის დასრულებაზე ფიქრობ, ახლავე დაელაპარაკე ვინმეს:
  დარეკე შენი ქვეყნის გადაუდებელ ნომერზე ან იპოვე უფასო დახმარების ხაზი
  https://findahelpline.com-ზე.

@lo ລາວ | wiki=lo | schrift=lao | nospace
hallo = ສະບາຍດີ; ສະບາຍດີຕອນເຊົ້າ; ສະບາຍດີຕອນແລງ
info = ເຈົ້າແມ່ນໃຜ; ເຈົ້າເຮັດຫຍັງໄດ້ແດ່; ຊ່ວຍເຫຼືອ
danke = ຂອບໃຈ; ຂອບໃຈຫຼາຍໆ; ຂອບໃຈຫລາຍ
tschuess = ລາກ່ອນ; ພົບກັນໃໝ່; ລາຕີສະຫວັດ
wiegehts = ສະບາຍດີບໍ່; ເປັນແນວໃດ; ເປັນຈັ່ງໃດ
wetter = ສະພາບອາກາດ; ອາກາດ; ອຸນຫະພູມ; ຝົນຕົກ
zeit = ຈັກໂມງແລ້ວ; ຕອນນີ້ຈັກໂມງ; ເວລາ
datum = ມື້ນີ້ວັນທີເທົ່າໃດ; ວັນທີ; ມື້ນີ້ແມ່ນມື້ຫຍັງ
heute = ມື້ນີ້
morgen = ມື້ອື່ນ
wiki = {x}ແມ່ນຫຍັງ; {x}ແມ່ນໃຜ; ບອກກ່ຽວກັບ{x}
stopp = ທີ່; ຂອງ; ໃນ; ເປັນແນວໃດ; ແນວໃດ; ບໍ່; ມື້ນີ້; ມື້ອື່ນ; ຕອນນີ້; ຈະ
krise = ຂ້າຕົວຕາຍ; ຢາກຕາຍ
A.intro = ສະບາຍດີ! ຂ້ອຍແມ່ນ Aquaticy Standard. ຂ້ອຍບອກສະພາບອາກາດ ເວລາ ແລະ ວັນທີໄດ້ ຄິດໄລ່ໄດ້
  ແລະ ຊອກຫາໃນວິກິພີເດຍໄດ້.
A.danke = ບໍ່ເປັນຫຍັງ!
A.tschuess = ລາກ່ອນ! ພົບກັນໃໝ່.
A.wiegehts = ສະບາຍດີ ຂອບໃຈ! ມີຫຍັງໃຫ້ຊ່ວຍບໍ່?
A.zeit = ຕອນນີ້ເວລາ {zeit}.
A.datum = ມື້ນີ້ແມ່ນ {datum}.
A.ort = ຢາກຮູ້ສະພາບອາກາດຢູ່ໃສ?
A.nichts = ຂໍອະໄພ ບໍ່ພົບຂໍ້ມູນກ່ຽວກັບ “{x}”.
A.rueckfall = ຂໍອະໄພ ຖ້າບໍ່ມີແບບຈຳລອງພາສາ ຂ້ອຍຕອບບໍ່ໄດ້. ລອງຖາມເລື່ອງສະພາບອາກາດ ເວລາ ວັນທີ
  ການຄິດໄລ່ ຫຼື ເລື່ອງໃນວິກິພີເດຍ.
A.krise = ເຈົ້າບໍ່ໄດ້ຢູ່ຄົນດຽວ. ຖ້າເຈົ້າກຳລັງຄິດຈະຈົບຊີວິດ ກະລຸນາລົມກັບໃຜຜູ້ໜຶ່ງດຽວນີ້:
  ໂທຫາເບີສຸກເສີນໃນປະເທດຂອງເຈົ້າ ຫຼື ຊອກຫາສາຍດ່ວນຊ່ວຍເຫຼືອຟຣີທີ່ https://findahelpline.com.

@tg Тоҷикӣ | wiki=tg | schrift=cyrillic
zeichen = ҳ;ҷ;ӣ;ӯ;қ;ғ
hallo = салом; ассалому алейкум; субҳ ба хайр; шом ба хайр
info = ту кистӣ; шумо кистед; чӣ кор карда метавонӣ; кӯмак
danke = ташаккур; раҳмат; ташаккури зиёд
tschuess = хайр; то дидан; шаб ба хайр; худо ҳофиз
wiegehts = чӣ хел; аҳволат чӣ хел; нағз ҳастӣ; чӣ гап
wetter = обу ҳаво; ҳаво; ҳарорат; борон
zeit = соат чанд аст; ҳозир соат чанд; вақт чанд аст
datum = имрӯз чандум аст; санаи имрӯза; имрӯз кадом рӯз аст
heute = имрӯз
morgen = фардо
wiki = {x} чист; {x} кист; дар бораи {x} гӯй
stopp = дар; ба; чӣ; хел; аст; мешавад; имрӯз; фардо; ҳозир; гӯй
krise = худкушӣ; мехоҳам бимирам; худамро кушам
A.intro = Салом! Ман Aquaticy Standard ҳастам. Ман метавонам обу ҳаво, вақт ва санаро гӯям, ҳисоб
  кунам ва дар Википедия ҷустуҷӯ кунам.
A.danke = Марҳамат!
A.tschuess = Хайр! То дидан.
A.wiegehts = Нағз ҳастам, ташаккур! Чӣ хел ёрӣ диҳам?
A.zeit = Ҳозир соат {zeit}.
A.datum = Имрӯз {datum}.
A.ort = Обу ҳавои кадом ҷойро бинам?
A.nichts = Бубахшед, дар бораи «{x}» чизе наёфтам.
A.rueckfall = Бубахшед, бе модели забонӣ ба ин ҷавоб дода наметавонам. Аз ман дар бораи обу ҳаво,
  вақт, сана, ҳисоб ё чизе аз Википедия пурсед.
A.krise = Шумо танҳо нестед. Агар дар бораи хотима додан ба ҳаётатон фикр кунед, ҳозир бо касе
  гап занед: ба рақами ёрии таъҷилии кишваратон занг занед ё дар https://findahelpline.com
  хати ёрии ройгон ёбед.

@tk Türkmençe | wiki=tk | schrift=latin
hallo = salam; salam aleýkum; ertiriňiz haýyrly; agşamyňyz haýyrly
info = sen kim; siz kim; näme edip bilýärsiň; kömek
danke = sag bol; sag boluň; minnetdar; köp sag bol
tschuess = hoş; görüşýänçä; gijäňiz rahat bolsun; sag bolaweri
wiegehts = nähili; ýagdaýlar nähili; gowumy; näme täzelik
wetter = howa; howa maglumaty; temperatura; ýagyş
zeit = sagat näçe; häzir sagat näçe; wagt näçe
datum = şu gün näçesi; şu günki sene; şu gün haýsy gün
heute = şu gün
morgen = ertir
wiki = {x} näme; {x} kim; {x} barada aýt
stopp = da; de; nähili; näme; şu; gün; ertir; bolar; häzir; howasy
krise = özümi öldürmek; ölesim gelýär
A.intro = Salam! Men Aquaticy Standard. Size howany, wagty we senäni aýdyp, hasaplap we
  Wikipediýada gözläp bilerin.
A.danke = Hiç zat däl!
A.tschuess = Hoş! Görüşýänçä.
A.wiegehts = Gowy, sag boluň! Size nähili kömek edip bilerin?
A.zeit = Häzir sagat {zeit}.
A.datum = Şu gün {datum}.
A.ort = Haýsy ýeriň howasyna seredeýin?
A.nichts = Bagyşlaň, “{x}” barada hiç zat tapmadym.
A.rueckfall = Bagyşlaň, dil modeli bolmasa men muňa jogap berip bilemok. Menden howa, wagt, sene,
  hasap ýa-da Wikipediýadan bir zat soraň.
A.krise = Siz ýeke däl. Eger durmuşyňyza nokat goýmagy pikir edýän bolsaňyz, häzir kimdir biri bilen
  gürleşiň: ýurduňyzyň gyssagly kömek belgisine jaň ediň ýa-da https://findahelpline.com
  sahypasynda mugt kömek liniýasyny tapyň.

@ky Кыргызча | wiki=ky | schrift=cyrillic
zeichen = ң;ө;ү
hallo = салам; саламатсызбы; кутман таң; кутман кеч; ассалому алейкум
info = сен кимсиң; сиз кимсиз; эмне кыла аласың; жардам
danke = рахмат; чоң рахмат; ыраазымын
tschuess = кош; жакшы кал; көрүшкөнчө; жакшы түн
wiegehts = кандайсың; кандайсыз; иштер кандай; жакшысыңбы
wetter = аба ырайы; аба-ырайы; температура; жамгыр
zeit = саат канча; азыр саат канча; убакыт канча
datum = бүгүн канчанчы; бүгүнкү дата; бүгүн кайсы күн
heute = бүгүн
morgen = эртең
wiki = {x} деген эмне; {x} эмне; {x} ким; {x} жөнүндө айт
stopp = да; де; та; те; кандай; эмне; бүгүн; эртең; болот; азыр; айтчы
krise = өзүмдү өлтүрүү; өлгүм келет; суицид
A.intro = Салам! Мен Aquaticy Standard. Сизге аба ырайын, убакытты жана датаны айта алам, эсептей
  алам жана Википедиядан издей алам.
A.danke = Эчтеке эмес!
A.tschuess = Кош! Көрүшкөнчө.
A.wiegehts = Жакшымын, рахмат! Сизге кантип жардам берейин?
A.zeit = Азыр саат {zeit}.
A.datum = Бүгүн {datum}.
A.ort = Кайсы жердин аба ырайын карайын?
A.nichts = Кечириңиз, «{x}» жөнүндө эч нерсе тапкан жокмун.
A.rueckfall = Кечириңиз, тил моделисиз буга жооп бере албайм. Менден аба ырайы, убакыт, дата,
  эсеп же Википедиядагы бир нерсе жөнүндө сураңыз.
A.krise = Сиз жалгыз эмессиз. Эгер өмүрүңүзгө чекит коюуну ойлоп жатсаңыз, азыр эле бирөө менен
  сүйлөшүңүз: өлкөңүздүн тез жардам номерине чалыңыз же https://findahelpline.com сайтынан
  акысыз жардам линиясын табыңыз.

@mn Монгол | wiki=mn | schrift=cyrillic
zeichen = ө;ү
hallo = сайн байна уу; сайн уу; өглөөний мэнд; оройн мэнд
info = чи хэн бэ; та хэн бэ; юу хийж чадах вэ; тусламж
danke = баярлалаа; их баярлалаа; гялайлаа
tschuess = баяртай; дараа уулзъя; сайхан амраарай
wiegehts = сайн байна уу; юу байна; ямар байна; сонин юу байна
wetter = цаг агаар; цаг агаарын мэдээ; температур; бороо
zeit = хэдэн цаг болж байна; хэдэн цаг вэ; цаг хэд болж байна
datum = өнөөдөр хэдэн бэ; өнөөдрийн огноо; өнөөдөр ямар өдөр вэ
heute = өнөөдөр
morgen = маргааш
wiki = {x} гэж юу вэ; {x} юу вэ; {x} хэн бэ; {x}-ийн тухай хэл
stopp = д; т; ын; ийн; ямар; вэ; бэ; өнөөдөр; маргааш; одоо; байх; байна
krise = амиа хорлох; үхмээр байна; өөрийгөө алах
A.intro = Сайн байна уу! Би Aquaticy Standard. Би танд цаг агаар, цаг, огноог хэлж, тооцоолж,
  Википедиагаас хайж чадна.
A.danke = Зүгээр зүгээр!
A.tschuess = Баяртай! Дараа уулзъя.
A.wiegehts = Сайн, баярлалаа! Танд юугаар туслах вэ?
A.zeit = Одоо {zeit} болж байна.
A.datum = Өнөөдөр {datum}.
A.ort = Аль газрын цаг агаарыг харах вэ?
A.nichts = Уучлаарай, «{x}»-ийн тухай юу ч олсонгүй.
A.rueckfall = Уучлаарай, хэлний загваргүйгээр үүнд хариулж чадахгүй. Надаас цаг агаар, цаг,
  огноо, тооцоо эсвэл Википедиагийн талаар асуугаарай.
A.krise = Та ганцаараа биш. Хэрэв амьдралаа дуусгах тухай бодож байвал яг одоо хэн нэгэнтэй
  ярилцаарай:
  улсынхаа яаралтай тусламжийн дугаар руу залгах эсвэл https://findahelpline.com сайтаас үнэгүй
  тусламжийн утас хайгаарай.

@ti ትግርኛ | wiki=ti | schrift=ethiopic
hallo = ሰላም ዶ; ከመይ ሓዲርካ; ከመይ ዊዒልካ; ሰላም ኣለኹም
info = መን ኢኻ; እንታይ ክትገብር ትኽእል; ሓገዝ
danke = የቐንየለይ; የቐንየለይ ብዙሕ; ብዙሕ የመስግን
tschuess = ደሓን ኩን; ኣብ ካልእ እንራኸብ; ደሓን ሕደር
wiegehts = ከመይ ኣለኻ; ከመይ ኣለኺ; ጽቡቕ ዲኻ
wetter = ኩነታት ኣየር; ኣየር; ሙቐት; ዝናብ
zeit = ሰዓት ክንደይ ኮይኑ; ክንደይ ሰዓት እዩ; ሕጂ ሰዓት ክንደይ እዩ
datum = ሎሚ ዕለት ክንደይ እዩ; ናይ ሎሚ ዕለት; ሎሚ እንታይ መዓልቲ እዩ
heute = ሎሚ
morgen = ጽባሕ
wiki = {x} እንታይ እዩ; {x} መን እዩ; ብዛዕባ {x} ንገረኒ
stopp = ኣብ; ናይ; ከመይ; እዩ; ክኸውን; ሎሚ; ጽባሕ; ሕጂ; ንገረኒ
krise = ነብሰይ ክቐትል; ክመውት እደሊ
A.intro = ሰላም! ኣነ Aquaticy Standard እየ። ኩነታት ኣየር፣ ሰዓትን ዕለትን ክነግረካ፣ ክቖጽር ከምኡውን ኣብ
  ዊኪፔድያ ክደሊ እኽእል እየ።
A.danke = ጸገም የለን!
A.tschuess = ደሓን ኩን!
A.wiegehts = ጽቡቕ እየ፣ የቐንየለይ! ብኸመይ ክሕግዘካ?
A.zeit = ሕጂ {zeit} እዩ።
A.datum = ሎሚ {datum} እዩ።
A.ort = ናይ ኣየናይ ቦታ ኩነታት ኣየር ክርኢ?
A.nichts = ይቕሬታ፣ ብዛዕባ “{x}” ዝኾነ ነገር ኣይረኸብኩን።
A.rueckfall = ይቕሬታ፣ ብዘይ ቋንቋ ሞዴል ነዚ ክምልሶ ኣይክእልን። ብዛዕባ ኩነታት ኣየር፣ ሰዓት፣ ዕለት፣
  ቁጽሪ ወይ ካብ ዊኪፔድያ ዝኾነ ነገር ሕተተኒ።
A.krise = በይንኻ ኣይኮንካን። ህይወትካ ከተብቅዕ እንተሓሲብካ፣ ሕጂ ምስ ሓደ ሰብ ተዘራረብ: ናብ ቁጽሪ ህጹጽ ረዲኤት
  ሃገርካ ደውል ወይ ኣብ https://findahelpline.com ናጻ መስመር ሓገዝ ድለ።

@om Afaan Oromoo | wiki=om | schrift=latin
hallo = akkam; nagaa; akkam jirta; akkam bulte; akkam oolte
info = ati eenyu; maal gochuu dandeessa; gargaarsa; na gargaari
danke = galatoomi; galatoomaa; baay'ee galatoomi
tschuess = nagaatti; nagaan bulaa; walitti deebinaa
wiegehts = akkam jirta; fayya qabdaa; akkam jirtu
wetter = haala qilleensaa; qilleensa; ho'a; rooba
zeit = sa'aatii meeqa; amma sa'aatii meeqa; yeroon meeqa
datum = har'a guyyaa meeqa; guyyaa har'aa; har'a guyyaa kam
heute = har'a
morgen = boru
wiki = {x} maali; {x} eenyu; waa'ee {x} natti himi
stopp = keessa; irratti; akkam; maal; har'a; boru; ta'a; amma
krise = of ajjeesuu; du'uu barbaada
A.intro = Akkam! Ani Aquaticy Standard dha. Haala qilleensaa, sa'aatii fi guyyaa sitti himuu,
  herreguu fi Wikipedia irratti barbaaduu nan danda'a.
A.danke = Rakkoo hin qabu!
A.tschuess = Nagaatti!
A.wiegehts = Nagaa dha, galatoomi! Akkamittan si gargaaruu danda'a?
A.zeit = Amma sa'aatii {zeit}.
A.datum = Har'a {datum}.
A.ort = Haala qilleensaa bakka kamii haa ilaalu?
A.nichts = Dhiifama, waa'ee “{x}” homaa hin arganne.
A.rueckfall = Dhiifama, moodela afaanii malee kanaaf deebii kennuu hin danda'u. Waa'ee haala
  qilleensaa, sa'aatii, guyyaa, herregaa ykn waan Wikipedia irraa na gaafadhu.
A.krise = Ati kophaa kee miti. Yoo lubbuu kee balleessuu yaadaa jirta ta'e, amma nama tokko
  dubbisi: lakkoofsa balaa biyya keetii bilbili ykn gargaarsa bilisaa https://findahelpline.com
  irratti barbaadi.

@lt Lietuvių | wiki=lt | schrift=latin
zeichen = ą;ę;ė;į;ų
hallo = labas; sveiki; laba diena; labas rytas; labas vakaras
info = kas tu esi; ką tu moki; ką gali padaryti; pagalba
danke = ačiū; labai ačiū; dėkoju; ačiū labai
tschuess = viso gero; iki; iki pasimatymo; labos nakties
wiegehts = kaip sekasi; kaip laikaisi; kaip tu; kaip gyveni
wetter = orai; oras; orų prognozė; temperatūra; lyja
zeit = kiek valandų; kelinta valanda; kiek dabar valandų
datum = kokia šiandien data; kelinta šiandien; kokia šiandien diena; šiandienos data
heute = šiandien
morgen = rytoj
wiki = kas yra {x}; kas buvo {x}; papasakok apie {x}
stopp = į; ant; kokie; koks; kaip; bus; šiandien; rytoj; dabar; yra
krise = nusižudyti; noriu mirti; savižudybė
A.intro = Labas! Aš esu Aquaticy Standard. Galiu pasakyti orus, laiką ir datą, skaičiuoti ir
  ieškoti Vikipedijoje.
A.danke = Prašom!
A.tschuess = Viso gero!
A.wiegehts = Man gerai, ačiū! Kuo galiu padėti?
A.zeit = Dabar {zeit}.
A.datum = Šiandien {datum}.
A.ort = Kokios vietos orus pažiūrėti?
A.nichts = Atsiprašau, apie „{x}“ nieko neradau.
A.rueckfall = Atsiprašau, be kalbos modelio į tai atsakyti negaliu. Paklausk manęs apie orus,
  laiką, datą, skaičiavimą ar ką nors iš Vikipedijos.
A.krise = Tu ne vienas. Jei galvoji apie tai, kad nutrauktum savo gyvenimą, pasikalbėk su kuo nors
  dabar: paskambink savo šalies skubios pagalbos numeriu arba rask nemokamą pagalbos liniją
  https://findahelpline.com.

@lv Latviešu | wiki=lv | schrift=latin
zeichen = ā;ē;ī;ū;ķ;ļ;ņ;ģ
hallo = sveiki; labdien; labrīt; labvakar; čau; sveiks
info = kas tu esi; ko tu proti; ko tu vari izdarīt; palīdzība
danke = paldies; liels paldies; pateicos
tschuess = uz redzēšanos; atā; ar labu nakti; tiksimies
wiegehts = kā tev iet; kā jums iet; kā klājas; kā sokas
wetter = laikapstākļi; laiks; laika prognoze; temperatūra; līst
zeit = cik ir pulkstenis; cik pulkstenis; cik ir laiks
datum = kāds šodien datums; kura diena šodien; šodienas datums
heute = šodien
morgen = rīt
wiki = kas ir {x}; kas bija {x}; pastāsti par {x}
stopp = uz; par; kāds; kādi; kā; būs; šodien; rīt; tagad; ir
krise = izdarīt pašnāvību; gribu nomirt; pašnāvība
A.intro = Sveiki! Es esmu Aquaticy Standard. Varu pateikt laikapstākļus, laiku un datumu, rēķināt
  un meklēt Vikipēdijā.
A.danke = Lūdzu!
A.tschuess = Uz redzēšanos!
A.wiegehts = Man iet labi, paldies! Kā varu palīdzēt?
A.zeit = Pulkstenis ir {zeit}.
A.datum = Šodien ir {datum}.
A.ort = Kuras vietas laikapstākļus apskatīt?
A.nichts = Atvainojiet, par „{x}” neko neatradu.
A.rueckfall = Atvainojiet, bez valodas modeļa uz to nevaru atbildēt. Jautājiet par laikapstākļiem,
  laiku, datumu, aprēķinu vai kaut ko no Vikipēdijas.
A.krise = Tu neesi viens. Ja domā par to, lai atņemtu sev dzīvību, runā ar kādu tūlīt: zvani savas
  valsts ārkārtas numuram vai atrodi bezmaksas palīdzības līniju https://findahelpline.com.

@sl Slovenščina | wiki=sl | schrift=latin
hallo = živjo; dober dan; dobro jutro; dober večer; zdravo; pozdravljeni
info = kdo si; kaj znaš; kaj lahko narediš; pomoč
danke = hvala; hvala lepa; najlepša hvala; hvala ti
tschuess = nasvidenje; adijo; lahko noč; se vidimo
wiegehts = kako si; kako ste; kako gre; kaj dogaja
wetter = vreme; vremenska napoved; temperatura; dežuje; dež
zeit = koliko je ura; koliko je sedaj ura; kateri čas je
datum = kateri datum je danes; kateri dan je danes; današnji datum
heute = danes
morgen = jutri
wiki = kaj je {x}; kdo je {x}; kdo je bil {x}; povej mi o {x}
stopp = v; na; za; kakšno; kako; bo; danes; jutri; sedaj; zdaj; je
krise = ubiti se; hočem umreti; samomor
A.intro = Živjo! Sem Aquaticy Standard. Lahko ti povem vreme, uro in datum, računam in iščem na
  Wikipediji.
A.danke = Ni za kaj!
A.tschuess = Nasvidenje!
A.wiegehts = Dobro sem, hvala! Kako lahko pomagam?
A.zeit = Ura je {zeit}.
A.datum = Danes je {datum}.
A.ort = Za kateri kraj naj preverim vreme?
A.nichts = Žal nisem našel ničesar o »{x}«.
A.rueckfall = Žal brez jezikovnega modela na to ne morem odgovoriti. Vprašaj me o vremenu, uri,
  datumu, izračunu ali čem z Wikipedije.
A.krise = Nisi sam. Če razmišljaš o tem, da bi si vzel življenje, se zdaj pogovori z nekom: pokliči
  številko za nujne primere v svoji državi ali poišči brezplačno linijo za pomoč na
  https://findahelpline.com.

@sq Shqip | wiki=sq | schrift=latin
zeichen = ë
hallo = përshëndetje; tungjatjeta; mirëdita; mirëmëngjes; mirëmbrëma; ç'kemi
info = kush je ti; çfarë mund të bësh; ndihmë; më ndihmo
danke = faleminderit; shumë faleminderit; flm; rrofsh
tschuess = mirupafshim; shihemi; natën e mirë; pafshim
wiegehts = si je; si jeni; si ia kalon; çfarë bën
wetter = moti; parashikimi i motit; temperatura; bie shi
zeit = sa është ora; sa ora është; ç'orë është
datum = çfarë date është sot; sa është data sot; çfarë dite është sot
heute = sot
morgen = nesër
wiki = çfarë është {x}; kush është {x}; kush ishte {x}; më trego për {x}
stopp = në; për; i; e; si; është; do; jetë; sot; nesër; tani; motin
krise = vras veten; dua të vdes; vetëvrasje
A.intro = Përshëndetje! Jam Aquaticy Standard. Mund të të them motin, orën dhe datën, të llogaris
  dhe të kërkoj në Wikipedia.
A.danke = S'ka përse!
A.tschuess = Mirupafshim!
A.wiegehts = Jam mirë, faleminderit! Si mund të të ndihmoj?
A.zeit = Ora është {zeit}.
A.datum = Sot është {datum}.
A.ort = Për cilin vend dëshiron motin?
A.nichts = Më vjen keq, nuk gjeta asgjë për „{x}”.
A.rueckfall = Më vjen keq, pa një model gjuhe nuk mund t'i përgjigjem kësaj. Më pyet për motin,
  orën, datën, një llogaritje ose diçka nga Wikipedia.
A.krise = Nuk je vetëm. Nëse po mendon t'i japësh fund jetës, fol me dikë tani: telefono numrin e
  urgjencës në vendin tënd ose gjej një linjë ndihme falas në https://findahelpline.com.

@mk Македонски | wiki=mk | schrift=cyrillic
zeichen = ѓ;ќ;ѕ;ј;љ;њ
hallo = здраво; добар ден; добро утро; добра вечер; поздрав
info = кој си ти; што знаеш; што можеш; помош
danke = благодарам; фала; многу благодарам; ти благодарам
tschuess = пријатно; збогум; се гледаме; добра ноќ
wiegehts = како си; како сте; што правиш; како оди
wetter = времето; временска прогноза; температура; врне
zeit = колку е часот; колку часот; кое е времето
datum = кој датум е денес; кој ден е денес; денешен датум
heute = денес
morgen = утре
wiki = што е {x}; кој е {x}; која е {x}; кој беше {x}; кажи ми за {x}
stopp = во; на; за; какво; како; ќе; биде; денес; утре; сега; е
krise = да се убијам; сакам да умрам; самоубиство
A.intro = Здраво! Јас сум Aquaticy Standard. Можам да ти кажам времето, часот и датумот, да
  пресметувам и да барам на Википедија.
A.danke = Нема зошто!
A.tschuess = Пријатно!
A.wiegehts = Добро сум, благодарам! Како можам да помогнам?
A.zeit = Часот е {zeit}.
A.datum = Денес е {datum}.
A.ort = За кое место да го проверам времето?
A.nichts = Извини, не најдов ништо за „{x}“.
A.rueckfall = Извини, без јазичен модел не можам да одговорам на ова. Прашај ме за времето,
  часот, датумот, пресметка или нешто од Википедија.
A.krise = Не си сам. Ако размислуваш да си го одземеш животот, разговарај со некого веднаш: јави се
  на бројот за итни случаи во твојата земја или најди бесплатна линија за помош на
  https://findahelpline.com.

@ca Català | wiki=ca | schrift=latin
zeichen = ·;ï
hallo = hola; bon dia; bona tarda; ei; salut
info = qui ets; què pots fer; què saps fer; ajuda
danke = gràcies; moltes gràcies; mercès; gràcies de debò
tschuess = adéu; fins aviat; a reveure; fins després; bona nit
wiegehts = com estàs; com va; què tal; com et va
wetter = quin temps fa; el temps; temps; previsió; temperatura; plou
zeit = quina hora és; quina hora; l'hora
datum = quin dia és avui; quina data és; la data d'avui
heute = avui
morgen = demà
wiki = què és {x}; qui és {x}; qui era {x}; parla'm de {x}
stopp = a; en; de; el; la; per; quin; quina; fa; farà; com; avui; demà; temps; ara
krise = suïcidar-me; vull morir; matar-me; treure'm la vida
A.intro = Hola! Soc Aquaticy Standard. Et puc dir el temps, l'hora i la data, fer càlculs i buscar
  a la Viquipèdia.
A.danke = De res!
A.tschuess = Adéu! Fins aviat.
A.wiegehts = Molt bé, gràcies! En què et puc ajudar?
A.zeit = Són les {zeit}.
A.datum = Avui és {datum}.
A.ort = De quin lloc vols saber el temps?
A.nichts = Ho sento, no he trobat res sobre «{x}».
A.rueckfall = Ho sento, sense un model de llenguatge no puc respondre això. Pregunta'm pel temps,
  l'hora, la data, un càlcul o alguna cosa de la Viquipèdia.
A.krise = No estàs sol. Si penses a treure't la vida, parla amb algú ara mateix: truca al número
  d'emergències del teu país o troba una línia d'ajuda gratuïta a https://findahelpline.com.

@af Afrikaans | wiki=af | schrift=latin
zeichen = ê;ë;ŉ
hallo = hallo; goeiemôre; goeiemiddag; goeienaand; haai; middag
info = wie is jy; wat kan jy doen; hulp; help my
danke = dankie; baie dankie; dankie tog
tschuess = totsiens; tot later; lekker slaap; sien jou later; mooi bly
wiegehts = hoe gaan dit; hoe gaan dit met jou; alles reg; hoe lyk dit
wetter = weer; die weer; weervoorspelling; temperatuur; reën
zeit = hoe laat is dit; hoe laat; tyd
datum = watter datum is dit; wat is die datum; watter dag is dit vandag
heute = vandag
morgen = môre
wiki = wat is {x}; wie is {x}; wie was {x}; vertel my van {x}
stopp = in; op; vir; die; hoe; is; gaan; wees; vandag; môre; nou; wat; weer; dit
krise = selfmoord; ek wil doodgaan; myself doodmaak
A.intro = Hallo! Ek is Aquaticy Standard. Ek kan jou die weer, die tyd en die datum vertel, reken en
  op Wikipedia soek.
A.danke = Plesier!
A.tschuess = Totsiens!
A.wiegehts = Dit gaan goed, dankie! Hoe kan ek help?
A.zeit = Dit is {zeit}.
A.datum = Vandag is dit {datum}.
A.ort = Vir watter plek wil jy die weer weet?
A.nichts = Jammer, ek het niks oor “{x}” gevind nie.
A.rueckfall = Jammer, sonder 'n taalmodel kan ek dit nie beantwoord nie. Vra my oor die weer, die
  tyd, die datum, 'n berekening of iets van Wikipedia.
A.krise = Jy is nie alleen nie. As jy daaraan dink om jou lewe te neem, praat nou met iemand: bel
  die noodnommer in jou land of vind 'n gratis hulplyn by https://findahelpline.com.
"""
