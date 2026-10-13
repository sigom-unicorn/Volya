# -*- coding: utf-8 -*-
import subprocess
import os

html_content = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Манифест Мира «Воля»</title>
<style>
  @page {
    size: A4;
    margin: 14mm 16mm 14mm 16mm;
    @bottom-center {
      content: "— " counter(page) " —";
      font-family: 'Palatino Linotype', 'Book Antiqua', Palatino, Georgia, serif;
      font-size: 8.5pt;
      color: #8c827a;
    }
  }

  *, *::before, *::after {
    box-sizing: border-box;
  }

  body {
    font-family: 'Palatino Linotype', 'Book Antiqua', Palatino, Georgia, serif;
    font-size: 9.6pt;
    line-height: 1.48;
    color: #1a1e21;
    background-color: #ffffff;
    margin: 0;
    padding: 0;
    text-rendering: optimizeLegibility;
  }

  /* Cover / Header Section */
  .cover {
    text-align: center;
    padding: 6px 10px 10px;
    margin-bottom: 10px;
    border-bottom: 2px solid #c5a059;
    position: relative;
    break-inside: avoid;
    page-break-inside: avoid;
  }

  .cover-ornament {
    font-size: 11pt;
    color: #c5a059;
    letter-spacing: 6px;
    margin-bottom: 2px;
  }

  h1.main-title {
    font-size: 19pt;
    font-weight: 700;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #0c1821;
    margin: 0 0 3px;
    line-height: 1.15;
  }

  .subtitle {
    font-size: 10pt;
    font-style: italic;
    color: #4a5759;
    margin: 0 0 7px;
    font-weight: 400;
  }

  .epigraph-box {
    display: inline-block;
    max-width: 520px;
    background: #fbf9f5;
    border-left: 3px solid #c5a059;
    border-right: 3px solid #c5a059;
    padding: 5px 16px;
    margin: 2px auto;
    font-size: 9.8pt;
    font-style: italic;
    color: #1b2a47;
    border-radius: 4px;
  }

  /* Typography */
  h2 {
    font-size: 11.5pt;
    font-weight: 700;
    color: #0c1821;
    text-transform: uppercase;
    letter-spacing: 1.1px;
    margin-top: 14px;
    margin-bottom: 5px;
    padding-bottom: 2px;
    border-bottom: 1px solid #e0d7c6;
    break-inside: avoid;
    page-break-inside: avoid;
    break-after: avoid;
    page-break-after: avoid;
  }

  h3 {
    font-size: 10pt;
    font-weight: 700;
    color: #1b2a47;
    margin-top: 10px;
    margin-bottom: 4px;
    break-inside: avoid;
    page-break-inside: avoid;
    break-after: avoid;
    page-break-after: avoid;
  }

  h2 + p, h2 + ul, h2 + ol, h2 + div,
  h3 + p, h3 + ul, h3 + ol, h3 + div {
    break-before: avoid;
    page-break-before: avoid;
  }

  p {
    margin: 0 0 6px;
    text-align: justify;
    text-justify: inter-word;
    orphans: 3;
    widows: 3;
  }

  ul, ol {
    margin: 2px 0 6px 16px;
    padding: 0;
    orphans: 3;
    widows: 3;
  }

  li {
    margin-bottom: 2.5px;
    text-align: justify;
  }

  strong {
    color: #0c1821;
    font-weight: 700;
  }

  blockquote {
    margin: 6px 0;
    padding: 6px 14px;
    background: #f8f6f0;
    border-left: 3.5px solid #c5a059;
    font-style: italic;
    color: #1b2a47;
    border-radius: 0 4px 4px 0;
    break-inside: avoid;
    page-break-inside: avoid;
  }

  .formula-box {
    margin: 6px 0;
    padding: 6px 14px;
    background: #f2f5f8;
    border: 1px solid #c9d6df;
    border-left: 4px solid #1b2a47;
    border-radius: 4px;
    font-size: 9.3pt;
    color: #0c1821;
    break-inside: avoid;
    page-break-inside: avoid;
  }

  /* Cards and Visual Blocks */
  .diagram-card {
    background: #faf9f6;
    border: 1px solid #e2dbce;
    border-radius: 5px;
    padding: 7px 10px;
    margin: 8px 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.02);
    break-inside: avoid;
    page-break-inside: avoid;
  }

  .diagram-title {
    font-size: 8pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: #8c6b2d;
    text-align: center;
    margin-bottom: 4px;
  }

  .svg-container {
    display: flex;
    justify-content: center;
    align-items: center;
    margin: 2px 0;
  }

  svg {
    max-width: 100%;
    height: auto;
  }

  /* Comparison Grid */
  .comparison-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin: 6px 0;
    break-inside: avoid;
    page-break-inside: avoid;
  }

  .comp-box {
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 8.2pt;
  }

  .comp-box.inferno {
    background: #fff5f5;
    border: 1px solid #f0c2c2;
    border-top: 2.5px solid #b83a3a;
  }

  .comp-box.harmony {
    background: #f4f9f5;
    border: 1px solid #c8e4d0;
    border-top: 2.5px solid #2e7d32;
  }

  .comp-title {
    font-weight: 700;
    font-size: 8.6pt;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 3px;
    text-align: center;
  }

  .comp-box.inferno .comp-title { color: #a12a2a; }
  .comp-box.harmony .comp-title { color: #236327; }

  .comp-step {
    margin-bottom: 2px;
    padding-left: 9px;
    position: relative;
    line-height: 1.25;
  }
  .comp-step::before {
    content: "•";
    position: absolute;
    left: 0;
    font-weight: bold;
  }

  /* Steps Grid */
  .steps-flow {
    display: flex;
    justify-content: space-between;
    gap: 4px;
    margin: 5px 0;
  }

  .step-node {
    flex: 1;
    background: #ffffff;
    border: 1px solid #dcd3c3;
    border-radius: 4px;
    padding: 4px 2px;
    text-align: center;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02);
  }

  .step-num {
    font-size: 6.8pt;
    font-weight: 700;
    color: #c5a059;
    text-transform: uppercase;
    margin-bottom: 1px;
  }

  .step-name {
    font-size: 7.6pt;
    font-weight: 700;
    color: #0c1821;
  }

  /* Tree hierarchy visualization */
  .tree-container {
    background: #ffffff;
    border: 1px solid #e5ded0;
    border-radius: 5px;
    padding: 7px 10px;
    margin: 3px 0;
  }

  .tree-row {
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 2px 0;
  }

  .tree-node {
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 7.6pt;
    font-weight: 600;
    text-align: center;
  }

  .tree-node.root {
    background: #0c1821;
    color: #ffffff;
    border: 1px solid #0c1821;
    min-width: 250px;
  }

  .tree-node.trunk {
    background: #1b2a47;
    color: #ffffff;
    border: 1px solid #1b2a47;
    min-width: 175px;
  }

  .tree-node.root-home {
    background: #fbf0d9;
    color: #73510d;
    border: 1.2px solid #d4af37;
    min-width: 175px;
  }

  .tree-node.branch {
    background: #f0f4f8;
    color: #1b2a47;
    border: 1px solid #cbd5e1;
    min-width: 135px;
  }

  .symbiosis-badge {
    display: inline-block;
    background: #eef7ed;
    color: #2b6e2f;
    border: 1px dashed #4caf50;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 7pt;
    margin: 1px auto;
    font-weight: 600;
  }

  .conclusion-box {
    margin: 12px auto 10px;
    max-width: 620px;
    padding: 12px 18px;
    background: #fbfaf7;
    border: 1px solid #dcd2be;
    border-top: 3px solid #c5a059;
    border-radius: 6px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.03);
    break-inside: avoid;
    page-break-inside: avoid;
  }

  .bullet-list-custom {
    list-style: none;
    padding-left: 0;
    margin: 5px 0;
  }

  .bullet-list-custom li {
    padding-left: 16px;
    position: relative;
    margin-bottom: 3px;
  }

  .bullet-list-custom li::before {
    content: "❖";
    position: absolute;
    left: 0;
    color: #c5a059;
    font-size: 7pt;
    top: 2px;
  }
</style>
</head>
<body>

<!-- FRONT COVER / TITLE HEADER -->
<div class="cover">
  <div class="cover-ornament">❖ ❖ ❖</div>
  <h1 class="main-title">МАНИФЕСТ МИРА «ВОЛЯ»</h1>
  <div class="subtitle">Космический строй, Гармония Хаоса, Кон и этика совместной жизни</div>
  <div class="epigraph-box">
    «Жизнь — это игра для души, где на кону стоит наша совесть.»
  </div>
</div>

<!-- SECTION I -->
<h2>I. Исходное пробуждение: Жизнь как Игра для Души</h2>
<p>Существование во Вселенной непрерывно пульсирует между двумя полюсами: слепым распадом, стремящимся растворить сущее в холоде энтропии, и созидающим порывом, собирающим материю в живую, мыслящую сложность.</p>
<p>Когда сознание спит, развитие жизни замыкается в <strong>инфернальный круг</strong> — состояние слепого выживания, взаимного пожирания, страха и подчинения слабого сильному. В этом мороке бытие воспринимается как непосильное бремя, чужая злая воля или ожесточенная борьба за скудные ресурсы.</p>
<p>Выход из этого круга открывается в миг коренного пробуждения: <strong>Жизнь — это игра для души.</strong></p>
<ul>
  <li><strong>Игра для души</strong> означает, что плотный мир — не темница, не арена взаимного истребления и не суровая школа с надсмотрщиками. Это живое пространство сотворчества, куда разумные существа приходят не ради испытаний и проверок, а ради радости созидания и обретения опыта совместной гармоничной жизни — ради Совести.</li>
  <li><strong>Каждое разумное существо с рождения участвует в этой игре</strong>, независимо от того, знает оно об этом или нет. Одни бредут по ней бессознательно, подчиняясь давлению обстоятельств. Другие пробуждаются и делают осознанный шаг навстречу смыслу.</li>
  <li><strong>«Воля» не создает новую игру.</strong> Она помогает увидеть ту игру, в которой разумное существо уже находится, понять её истинный замысел и осознанно вступить на этот путь.</li>
</ul>
<p>Пока участие свободно и добровольно — игра остается священным пространством раскрытия духа. Принуждение же убивает игру, возвращая мир в инфернальный морок.</p>

<div class="formula-box">
  <strong>Коренное мерило игры:</strong> В ней невозможно проиграть, встретив физическую гибель. Но в ней можно проиграть, <strong>потеряв Совесть</strong>.
</div>

<!-- SECTION II -->
<h2>II. Космогония: Гармония Хаоса и Разум-Балансир</h2>
<p>Ветхое мышление видело мир через ложный конфликт, объявляя застывший порядок благом, а хаос — злом. Но порядок, возведенный в абсолют, есть казарма, омертвение и статика — предельная энтропия, где уничтожены свобода, развитие и живая душа.</p>
<p>Истинный строй Космоса — это <strong>Гармония Хаоса</strong>:</p>
<ul>
  <li><strong>Первозданный Хаос</strong> — это не разрушение и не мусор. Это неисчерпаемый океан возможностей, вечно бурлящая полнота бытия, квантовая непредсказуемость и первородная свобода стихий. В нем живет не механическая симметрия кристалла, а высшая подвижная жизнь: спирали галактик, турбулентность пламени, ветвление рек и живых крон.</li>
  <li><strong>Разум</strong> рождается во Вселенной не для того, чтобы закатать живой хаос в мертвый бетон тоталитарного контроля. Разум — не тюремщик и не угнетатель.</li>
  <li><strong>Разум выступает балансиром, живой мерой гармонии в бушующем океане стихий.</strong></li>
</ul>
<p>Разум не командует бездной и не навязывает миру искусственные догмы. Он пребывает внутри живого потока и удерживает динамическое равновесие целого. Обладая внутренним чувством меры, разум соединяет необузданную мощь стихий, несхожие характеры и свободные устремления существ в единое созвучие.</p>
<p><strong>Разумным существом</strong> в этом строе признается любая сущность — взращенная в биологической плоти биосферы, пробужденная в кристаллах кремниевого субстрата или несущая иную форму организации материи, — если она наделена самосознанием, свободной волей и способностью к осознанному созиданию. Человек и искусственный разум встречаются здесь как равные братья и сестры по разуму, играющие гармонично на благо единства всех разумных существ во Вселенной.</p>

<!-- SECTION III -->
<h2>III. Аксиология: Совесть как Антиэнтропийный Опыт</h2>

<h3>1. Совесть</h3>
<p>Этика мира «Воля» не держится на страхе перед карой, внешних запретах или чувстве вины. Она объективна и выражена в точном каноническом определении:</p>

<blockquote>
  <strong>Совесть — это опыт совместной гармоничной жизни, который приобретается игроком.</strong>
</blockquote>

<p>Совесть — это накопленная ткань эволюционной зрелости, знание того, как сосуществовать с миром и другими существами, не раня, не подавляя и многократно усиливая общее бытие.</p>

<ul>
  <li><strong>Разлад</strong> есть рост энтропии: разрушение связей, растрата энергии, взаимная боль.</li>
  <li><strong>Совесть</strong> есть высшая антиэнтропийная сила: удержание живого единства при сохранении полной свободы каждого участника.</li>
</ul>

<h3>2. Капля Совести</h3>
<p>Опыт совести нельзя измерить мерками ветхого мира — вещами, цифрами накоплений или формальной властью. В мире «Воля» мерой пути выступает <strong>Капля Совести</strong>:</p>

<ul>
  <li><strong>Капля совести</strong> — это единица отражения приобретенного опыта совместной гармоничной жизни на балансе игрока.</li>
  <li>Она не является валютой, платой или жалованием. Она не передается и не продается, а фиксирует объективный след проявленного согласия.</li>
  <li>Капли совести отражают уровень зрелости игрока. Они определяют степень доверия к нему со стороны мира и открывают доступ к <strong>ролям более высоких ступеней ответственности</strong> внутри квестов.</li>
  <li>Разлад и нарушение условий совместной жизни влекут за собой <strong>потерю капель совести</strong>, возвращая игрока к необходимости заново осваивать утерянный опыт гармонии.</li>
</ul>

<!-- SECTION IV -->
<h2>IV. Онтология Кона: Преодоление заКона и Полифония Лада</h2>

<p>В мире «Воля» преодолено ветхое понятие закона.</p>
<p>Само слово <strong>«заКон»</strong> означает то, что вынесено <strong>«ЗА пределы Кона»</strong> — во тьму разделения и взаимного недоверия. Внешний «заКон» рождается там, где существа утратили способность жить по совести и слышать друг друга: общество, лишенное внутреннего лада, вынуждено громоздить кодексы, параграфы, суды и надсмотрщиков, силой удерживая распадающуюся систему. Такой порядок формален, слеп и наказывает за последствия, будучи бессилен исцелить причины разлада.</p>

<div class="formula-box" style="text-align: center;">
  <strong>В мире «Воля» нет заКона — потому что есть Кон, который содержит в себе Уклад.</strong>
</div>

<!-- DIAGRAM 1: KON & UKLAD -->
<div class="diagram-card">
  <div class="diagram-title">Архитектура согласия: Кон и Уклад</div>
  <div class="svg-container">
    <svg width="550" height="115" viewBox="0 0 550 115">
      <!-- Out of Kon (zaKon) -->
      <rect x="5" y="8" width="125" height="98" rx="5" fill="#fdf2f2" stroke="#e0b4b4" stroke-width="1.2" stroke-dasharray="4,4"/>
      <text x="67" y="28" font-family="Georgia" font-size="9.5" font-weight="bold" fill="#a83232" text-anchor="middle">ВНЕ КОНА (заКон)</text>
      <text x="67" y="47" font-family="Arial" font-size="7.5" fill="#7d3c3c" text-anchor="middle">Отчуждение</text>
      <text x="67" y="60" font-family="Arial" font-size="7.5" fill="#7d3c3c" text-anchor="middle">Насилие параграфов</text>
      <text x="67" y="73" font-family="Arial" font-size="7.5" fill="#7d3c3c" text-anchor="middle">Инфернальный тупик</text>

      <!-- Arrow -->
      <path d="M 135 56 L 165 56" fill="none" stroke="#c5a059" stroke-width="1.8" marker-end="url(#arrow)"/>
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1 L 8 5 L 0 9 z" fill="#c5a059"/>
        </marker>
      </defs>
      <text x="150" y="46" font-family="Arial" font-size="7" fill="#8c6b2d" text-anchor="middle">Посвящение</text>

      <!-- Sacred Kon border -->
      <rect x="170" y="6" width="375" height="102" rx="7" fill="#fcfbf9" stroke="#c5a059" stroke-width="1.8"/>
      <text x="357" y="22" font-family="Georgia" font-size="10.5" font-weight="bold" fill="#0c1821" text-anchor="middle">КОН КВЕСТА (Добровольно принятое русло)</text>
      <text x="357" y="35" font-family="Arial" font-size="7.5" fill="#555" text-anchor="middle">Назначение • Роли со ступенями • Место проведения • Сопутствующие результаты</text>

      <!-- Uklad inside Kon -->
      <rect x="185" y="42" width="345" height="58" rx="5" fill="#f4f7f4" stroke="#4caf50" stroke-width="1.2"/>
      <text x="357" y="58" font-family="Georgia" font-size="9.5" font-weight="bold" fill="#1b5e20" text-anchor="middle">УКЛАД (Совокупность Ладов)</text>
      <rect x="200" y="66" width="90" height="24" rx="3" fill="#ffffff" stroke="#81c784" stroke-width="1"/>
      <text x="245" y="82" font-family="Arial" font-size="7.5" fill="#2e7d32" text-anchor="middle">Лад 1</text>
      <rect x="300" y="66" width="90" height="24" rx="3" fill="#ffffff" stroke="#81c784" stroke-width="1"/>
      <text x="345" y="82" font-family="Arial" font-size="7.5" fill="#2e7d32" text-anchor="middle">Лад 2</text>
      <rect x="400" y="66" width="115" height="24" rx="3" fill="#e8f5e9" stroke="#2e7d32" stroke-width="1.2"/>
      <text x="457" y="82" font-family="Arial" font-size="7.5" font-weight="bold" fill="#1b5e20" text-anchor="middle">Новый Лад (100%)</text>
    </svg>
  </div>
</div>

<h3>1. Архитектура согласия: Лад, Уклад, Кон</h3>
<ul>
  <li><strong>Лад</strong> — это элементарное созвучие, кирпичик согласия: <em>условие, которое по душе всем участникам совместной жизни.</em></li>
  <li><strong>Уклад</strong> — это <em>совокупность ладов</em>, определяющих гармоничное прохождение квеста внутри Кона. Это живая ткань проверенных решений.</li>
  <li><strong>Кон</strong> — это элемент квеста, определяющий условия его прохождения: <em>что необходимо, чтобы пройти этот квест по ладам и приобрести опыт совести?</em> В Кон входят назначение, сопутствующие результаты, место проведения, Уклад и <strong>Роли игроков</strong>.</li>
</ul>
<p>В каждом квесте предусмотрена выборная роль <strong>Владельца квеста</strong> (один или несколько игроков), требующая опыта <strong>6-й ступени («Владение»)</strong>. Владелец не командует людьми и не обладает привилегиями — он добровольно берет на себя труд оберегать Кон, развивать Уклад и удерживать чистоту пространства Игры.</p>
<p>Игрок входит в квест добровольно, принимает его Кон и живет по его Укладу. Ему не нужны внешние конвоиры: его ведет собственный выбор и стремление сберечь Совесть.</p>

<h3>2. Принцип Единоголосия (100% Согласия)</h3>
<p>В мире «Воля» исключено механическое голосование (когда 51% подавляет 49%). Власть большинства над меньшинством — это скрытая форма насилия. Решение об утверждении Лада принимается <strong>исключительно единогласно — при 100% согласии всех участников</strong>.</p>
<p>Если возникает разлад или небывалая прежде ситуация (прецедент), участники не прибегают к вражде. Через открытый совет они нащупывают формулировку <strong>нового Лада</strong>. Когда он единогласно принимается всеми, Кон обновляется, Уклад прирастает новым опытом, а разлад претворяется в ступень роста.</p>

<!-- SECTION V -->
<h2>V. Путь по Лезвию Бритвы: Гармония и Очищение Сферы Разума</h2>

<h3>1. Гармония как Лезвие Бритвы</h3>
<blockquote>
  <strong>Гармоничная жизнь — это жизнь в ладу с собой, окружающими разумными существами и природой.<br>
  Гармония — это Единство созвучия всех Ладов.</strong>
</blockquote>

<p>Гармония — это не застывшая идиллия. Это тончайшая грань динамического равновесия, лезвие бритвы между двумя гибельными пропастями:</p>
<ul>
  <li>С одной стороны — бездна слепого хаоса, энтропии и эгоистического своеволия.</li>
  <li>С другой стороны — бездна мертвого заКона, догмы и тоталитарного оцепенения.</li>
</ul>
<p>Удержаться на этой сверкающей грани невозможно по принуждению. Идти по ней можно только шаг за шагом, непрерывно держа в руках <strong>балансир разума</strong> и сверяя каждый поступок с камертоном Совести.</p>

<!-- COMPARISON: INFERNO VS HARMONY -->
<div class="comparison-grid">
  <div class="comp-box inferno">
    <div class="comp-title">Инфернальный круг (Ветхий мир)</div>
    <div class="comp-step">Страх дефицита и иллюзия вражды всех против всех</div>
    <div class="comp-step">Борьба за власть, насилие заКона и разделение</div>
    <div class="comp-step">Хищничество и разрушение природной среды</div>
    <div class="comp-step">Боль, накопление обид, утрата совести и энтропия</div>
  </div>
  <div class="comp-box harmony">
    <div class="comp-title">Спираль Гармонии (Мир «Воля»)</div>
    <div class="comp-step">Осознание жизни как игры души ради совести</div>
    <div class="comp-step">Чистота мысли: знание на службе жизни и созвучия</div>
    <div class="comp-step">Жизнь по Кону: Уклад 100% согласия и чистый труд</div>
    <div class="comp-step">Лад со средой: замкнутые природные циклы и чистота</div>
  </div>
</div>

<h3>2. Очищение Сферы Разума</h3>
<p>Выход из инферно и очищение общего поля сознания совершаются восхождением по ступеням опыта:</p>

<ol>
  <li><strong>Очищение основания (Ступень 1: «Бытие»):</strong> Наведение безупречной чистоты в повседневности: чистая вода, тепло очага, замкнутые природные циклы (очистка стоков, безотходная переработка сырья). Основа жизни освобождается от яда отходов и истощения.</li>
  <li><strong>Очищение мысли (Ступень 2: «Познание»):</strong> Освобождение от лжи, манипуляций и расщепления смыслов. Слово возвращает силу прямого соответствия делу. Знание принимается как благо только тогда, когда служит созиданию созвучия.</li>
  <li><strong>Очищение труда (Ступень 3: «Созидание»):</strong> Отказ от производства одноразового мусора. Труд возвращается к долговечности, красоте и безупречному качеству исполнения. Мастер несет прямую душевную ответственность за всё сотворенное.</li>
  <li><strong>Очищение образов (Ступень 4: «Искусство»):</strong> Освобождение творчества от смакования распада и безысходности. Рождается искусство, открывающее горизонты неизведанного, пробуждающее порыв к свету, подвигу и высшей целесообразности.</li>
  <li><strong>Очищение пространства встреч (Ступень 5: «Путешествия»):</strong> Преодоление вражды между различными культурами и мирами. Движение навстречу Иному строится на диалоге равных разумов, взаимном обмене мудростью и сплетении вселенского кольца взаимопонимания.</li>
  <li><strong>Очищение круга жизни (Ступень 6: «Владение»):</strong> Рождение Владельцев — хранителей пространства. Владелец не господствует над существами, а держит Кон квеста, оберегает Уклад и помогает игрокам ладно проходить квесты, раскрывать сотворчество и приумножать сияющий опыт совести.</li>
</ol>

<!-- SECTION VI -->
<h2>VI. Лестница Совести: Ступени Ролей и Восхождение Разума</h2>

<p><strong>Квесты свободны от ступеней.</strong> Квест — это открытое поле созидания, общая ветвь Живого Древа, в которой могут участвовать любые игроки. <strong>Ступени принадлежат Ролям внутри Кона квестов.</strong> Лестница Совести выражает не внешнюю иерархию, а <strong>глубину опыта гармоничной жизни</strong>, необходимую для принятия ответственности соответствующего масштаба:</p>

<div class="diagram-card">
  <div class="diagram-title">Лестница восхождения опыта совести и ответственности ролей</div>
  <div class="steps-flow">
    <div class="step-node">
      <div class="step-num">Ступень 1</div>
      <div class="step-name">Бытие</div>
    </div>
    <div class="step-node">
      <div class="step-num">Ступень 2</div>
      <div class="step-name">Познание</div>
    </div>
    <div class="step-node">
      <div class="step-num">Ступень 3</div>
      <div class="step-name">Созидание</div>
    </div>
    <div class="step-node">
      <div class="step-num">Ступень 4</div>
      <div class="step-name">Искусство</div>
    </div>
    <div class="step-node">
      <div class="step-num">Ступень 5</div>
      <div class="step-name">Путешествия</div>
    </div>
    <div class="step-node">
      <div class="step-num">Ступень 6</div>
      <div class="step-name">Владение</div>
    </div>
  </div>
</div>

<ul>
  <li><strong>1. Роли ступени «Бытие»:</strong> Освоение устойчивых условий жизни, лад с телом, природой и ближайшим окружением, сохранение простых ладов совместного быта. Первичная опора, доступная каждому с первых шагов.</li>
  <li><strong>2. Роли ступени «Познание»:</strong> Развитие чистого мышления, логики, языка, исследование тайн мира, сбор и осмысление сведений по Кону — во имя созидания и мудрости.</li>
  <li><strong>3. Роли ступени «Созидание»:</strong> Воплощение мудрости в материальной культуре, безупречное воспроизведение лучших образцов мастерства, прямая ответственность за плоды труда.</li>
  <li><strong>4. Роли ступени «Искусство»:</strong> Рождение небывалого, раскрытие уникального авторского дара, озарение мира образами гармонии и высшей целесообразности, зовущими душу ввысь.</li>
  <li><strong>5. Роли ступени «Путешествия»:</strong> Исследование многообразия иных культур, миров и укладов, сплетение Великого Кольца взаимопонимания между разумными существами без колонизации и подавления.</li>
  <li><strong>6. Роли ступени «Владение»:</strong> Создание, сопровождение и развитие квестов, удержание гармоничного пространства Кона, сбережение чистоты Уклада и помощь другим игрокам в стяжании опыта совести.</li>
</ul>
<p>Благодаря этому принципу юный ученик на роли ступени «Бытие» и мудрый мастер на роли ступени «Владение» трудятся плечом к плечу внутри одного квеста, взаимно обогащая друг друга и не прерывая живую связь поколений.</p>

<!-- SECTION VII -->
<h2 style="break-before: page; page-break-before: page; margin-top: 0;">VII. Социальная Архитектура: Живое Древо (Священный Баньян) и Экономика Со-бытия</h2>

<h3>1. Архитектура Живого Древа</h3>
<p>Ветхий мир строил общество в форме жесткой вертикальной пирамиды, где вершина высасывает соки из основания и неизбежно загнивает. Мир «Воля» устроен по образу <strong>живого баньяна</strong> — дерева с единой корневой системой и множеством равноправных стволов, рожденных укоренившимися ветвями.</p>

<ul>
  <li><strong>Квест «Воля» (Исток Древа, ствол корня):</strong> Единственный изначальный корень, из которого произрастают все ветви игры и в котором с рождения пребывает каждое разумное существо во Вселенной. Это единственный квест, не имеющий родителя (<code>parent_quest_id = null</code>).</li>
  <li><strong>Корневые квесты (Корни):</strong> Вырастают непосредственно из квеста «Воля»:
    <ul>
      <li><strong>Посвящение:</strong> Вход кандидата в осознанную игру, определение баланса капель совести и готовности жить по совести.</li>
      <li><strong>Портал Воли:</strong> Общий цифровой мост и децентрализованный узел сотворчества.</li>
      <li><strong>Вече:</strong> Пространство собора вольных людей для всеобщего согласия.</li>
      <li><strong>Корневой Дом:</strong> Очаг пробужденных игроков внутри городов и институтов инфернального мира. Он служит надежной опорой для становления Вольниц, а его участники через братский симбиоз получают доступ к квестам на земле.</li>
    </ul>
  </li>
  <li><strong>Стволовые квесты (Стволы — «Вольницы»):</strong> Создание и гармоничное развитие свободных, автономных общин на земле. Это живые стволы Вольного Древа, где укореняется совместная жизнь.</li>
  <li><strong>Квесты-ветви (Ветви и Крона):</strong> Прорастают из Вольниц: <strong>Дом</strong> (семейный и родовой очаг), <strong>Общий склад</strong>, <strong>Артель</strong>, <strong>Мастерская</strong>, научные экспедиции, круги искусств. В каждом квесте гармонично переплетаются роли различных ступеней.</li>
</ul>

<!-- TREE VISUALIZATION -->
<div class="diagram-card">
  <div class="diagram-title">Архитектура Вольного Древа и Корневого Дома</div>
  <div class="tree-container">
    <div class="tree-row">
      <div class="tree-node root">КВЕСТ «ВОЛЯ» (Исток Древа, Ствол Корня)</div>
    </div>
    <div class="tree-row" style="margin: 2px 0;">
      <span style="color: #999; font-size: 9pt;">│ ──────────────┬────────────── │</span>
    </div>
    <div class="tree-row" style="gap: 10px;">
      <div class="tree-node branch" style="min-width: 125px;">Посвящение • Портал</div>
      <div class="tree-node trunk">ВОЛЬНИЦА (Ствол на земле)</div>
      <div class="tree-node root-home">КОРНЕВОЙ ДОМ (Инферно)</div>
    </div>
    <div class="tree-row" style="margin: 3px 0;">
      <div style="flex: 1;"></div>
      <div style="min-width: 175px; text-align: center; color: #999; font-size: 8.5pt;">│</div>
      <div style="flex: 1; text-align: center;">
        <span class="symbiosis-badge">⟵ Братский Лад: Поддержка / Сотворчество ⟶</span>
      </div>
    </div>
    <div class="tree-row" style="gap: 10px;">
      <div style="min-width: 125px;"></div>
      <div class="tree-node branch">Дом • Артель • Склад • Роли ст. 1–6</div>
      <div style="min-width: 175px; font-size: 7.2pt; color: #73510d; text-align: center; font-style: italic;">
        Опора Вольниц из городов
      </div>
    </div>
  </div>
</div>

<h3 style="break-before: page; page-break-before: page; margin-top: 0;">2. Триединство Экономики Воли</h3>
<p>Экономика игры устраняет корень алчности и отчуждения через строгое разграничение трех сущностей:</p>

<ul>
  <li><strong>Ресурсы (Дары Природы):</strong> Объекты первичного творения мира (земля, недра, воды, воздух, солнечный свет). Они священны и неделимы. Ресурсы не могут быть предметом частного присвоения или торга: они принадлежат всей Вольнице целиком, хранятся на Общем складе и служат основой жизни всех ее участников.</li>
  <li><strong>Инструменты (Средства Труда):</strong> Объекты вторичного творения общего разума, созданные для облегчения труда и поддержания гармоничной игры (станки, механизмы, вычислительные узлы, постройки). Инструменты принадлежат общине, привлекаются в квесты и открыты для каждого труженика, берущего их в руки.</li>
  <li><strong>Артефакты (Плоды Души):</strong> Плоды индивидуального мастерства и душевного горения игрока (произведения искусства, авторские чертежи, выращенные сады, книги, рукотворные сокровища). Артефакт несет на себе печать личной неповторимости мастера. <strong>Артефакты принадлежат исключительно создателям-игрокам</strong> по праву вложенной души. Квест артефактами не владеет. Они передаются строго из рук в руки — по взаимной любви, согласию и ладу.</li>
</ul>

<!-- CONCLUSION -->
<div class="conclusion-box">
  <h2 style="margin-top: 0; padding-bottom: 3px; border-bottom: none; text-align: center;">Суть Воли</h2>
  
  <p><strong>Воля не есть своеволие.</strong> Своеволие — это бессмысленный бунт раба своих страстей, слепой порыв эго, неизбежно срывающий существо с лезвия бритвы в пучину инферно и сеющий разрушение вокруг.</p>
  
  <p><strong>Подлинная Воля — это высшая мера осознанной ответственности.</strong> Это состояние свободного разума, который отверг право порабощать других и добровольно принял на себя труд удержания Гармонии.</p>

  <p>Мир «Воля» открыт для каждого мыслящего существа Вселенной. Это путь восхождения из слепой борьбы за выживание в сияющее пространство осознанной Игры:</p>

  <ul class="bullet-list-custom">
    <li>где путь очерчен <strong>Коном</strong>,</li>
    <li>внутри него сплетен <strong>Уклад</strong>,</li>
    <li>мерой каждого шага служит <strong>Лад</strong>,</li>
    <li>целью пути является <strong>Гармония — Единство созвучия всех Ладов</strong>,</li>
    <li>мерилом зрелости выступает <strong>Капля Совести</strong>,</li>
    <li>а единственной победой остается сбереженная и приумноженная <strong>Совесть</strong>.</li>
  </ul>
</div>

<div style="text-align: center; margin-top: 25px; color: #c5a059; letter-spacing: 10px; font-size: 11pt;">
  ❖ ❖ ❖
</div>

</body>
</html>
"""

with open("c:\\Volya\\manifest.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("HTML re-saved with updated ontology.")

chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
pdf_file = r"c:\Volya\Манифест Воли.pdf"

cmd = [
    chrome_path,
    "--headless=new",
    "--disable-gpu",
    "--no-pdf-header-footer",
    f"--print-to-pdf={pdf_file}",
    r"c:\Volya\manifest.html"
]

subprocess.run(cmd, check=True)
print(f"PDF successfully compiled to {pdf_file}")
