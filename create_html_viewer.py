import base64

with open('c:/Volya/symbol_volya_torus.jpg', 'rb') as f:
    b64_torus = base64.b64encode(f.read()).decode('utf-8')

with open('c:/Volya/symbol_volya_harmonic.jpg', 'rb') as f:
    b64_column = base64.b64encode(f.read()).decode('utf-8')

html_content = f'''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Символ Воли — Колонна и Закольцованный Тор</title>
<style>
  body {{
    background-color: #0b0c10;
    color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    margin: 0;
    padding: 30px;
    display: flex;
    flex-direction: column;
    align-items: center;
  }}
  h1 {{ margin-bottom: 8px; color: #f8fafc; font-size: 26px; letter-spacing: 0.5px; }}
  p.subtitle {{ color: #94a3b8; font-size: 15px; margin-top: 0; margin-bottom: 28px; text-align: center; max-width: 680px; line-height: 1.5; }}
  .grid {{
    display: flex;
    flex-direction: column;
    gap: 36px;
    max-width: 680px;
    width: 100%;
  }}
  .card {{
    background: #141720;
    border: 1px solid #282f42;
    border-radius: 18px;
    padding: 24px;
    box-shadow: 0 12px 35px rgba(0,0,0,0.6);
    display: flex;
    flex-direction: column;
    align-items: center;
    box-sizing: border-box;
  }}
  .card img {{
    max-width: 100%;
    height: auto;
    border-radius: 12px;
    box-shadow: 0 6px 25px rgba(0,0,0,0.7);
    display: block;
  }}
  .card h2 {{ font-size: 20px; margin: 18px 0 8px 0; color: #f1f5f9; }}
  .card p {{ font-size: 14px; color: #94a3b8; margin: 0; line-height: 1.5; text-align: center; }}
  .legend {{
    display: flex;
    gap: 16px;
    margin-top: 14px;
    flex-wrap: wrap;
    justify-content: center;
  }}
  .item {{
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 500;
  }}
  .dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
  .badge {{
    background: rgba(168, 85, 247, 0.2);
    color: #c084fc;
    border: 1px solid rgba(168, 85, 247, 0.4);
    font-size: 12px;
    padding: 4px 14px;
    border-radius: 20px;
    margin-top: 12px;
  }}
</style>
</head>
<body>
  <h1>Символ Мира «Воля»</h1>
  <p class="subtitle">Два проявления одной формулы: Восходящая Колонна (Стрела Эволюции) и Закольцованный Тор (Великое Кольцо Кона)</p>

  <div class="grid">
    <div class="card">
      <img src="data:image/jpeg;base64,{b64_torus}" alt="Закольцованный Тор — Венец Кона" />
      <h2>1. Закольцованный Тор: Венец Кона (Великое Кольцо)</h2>
      <p>Три спирали замкнуты в непрерывный тороидальный вихрь. Ровно <b>6 симметричных лепестков-пересечений</b> соответствуют 6 Ступеням мира «Воля». Внутри кольца фиолетовая волна непрерывно пульсирует с удвоенной частотой, связывая золото и зелень в вечный неразрывный союз.</p>
      <div class="badge">Закольцованная форма (Тор / Венец Кона)</div>
      <div class="legend">
        <span class="item"><span class="dot" style="background:#a855f7;"></span> Центр: Волна Совести (2x)</span>
        <span class="item"><span class="dot" style="background:#f5b92d;"></span> Золотая лента</span>
        <span class="item"><span class="dot" style="background:#10b981;"></span> Зелёная лента</span>
      </div>
    </div>

    <div class="card">
      <img src="data:image/jpeg;base64,{b64_column}" alt="Вертикальная Колонна Восхождения" />
      <h2>2. Вертикальная Колонна: Путь Восхождения</h2>
      <p>Та же система в линейном развёртывании: стрела эволюции духа от 1-й ступени («Бытие») вверх к 6-й ступени («Владение»).</p>
      <div class="badge">Линейная форма (Стоячая волна)</div>
    </div>
  </div>
</body>
</html>
'''

with open('c:/Volya/view_symbol.html', 'w', encoding='utf-8') as f:
    f.write(html_content)

print("Updated view_symbol.html with Torus and Column!")
