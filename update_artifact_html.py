import base64

brain_dir = r'C:\Users\Polina\.gemini\antigravity\brain\9bbaed5b-a0e9-4089-90cf-57abd82f45e9'
img_path = r'c:\Volya\symbol_volya_harmonic.jpg'

with open(img_path, 'rb') as f:
    b64 = base64.b64encode(f.read()).decode('utf-8')

html = f'''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Символ Воли</title>
<style>
  body {{
    background-color: #0b0c10;
    color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    margin: 0;
    padding: 24px;
    display: flex;
    flex-direction: column;
    align-items: center;
  }}
  .card {{
    background: #141720;
    border: 1px solid #282f42;
    border-radius: 18px;
    padding: 24px;
    max-width: 650px;
    width: 100%;
    box-shadow: 0 12px 35px rgba(0,0,0,0.6);
    display: flex;
    flex-direction: column;
    align-items: center;
    box-sizing: border-box;
  }}
  img {{
    max-width: 100%;
    height: auto;
    border-radius: 12px;
    box-shadow: 0 6px 25px rgba(0,0,0,0.7);
    display: block;
  }}
  h1 {{ font-size: 22px; color: #f8fafc; margin: 0 0 8px 0; }}
  p {{ font-size: 14px; color: #94a3b8; margin: 0 0 20px 0; text-align: center; }}
  .legend {{
    display: flex;
    gap: 16px;
    margin-top: 18px;
    flex-wrap: wrap;
    justify-content: center;
    font-size: 13px;
  }}
  .dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 6px; }}
</style>
</head>
<body>
  <div class="card">
    <h1>Символ Мира «Воля»</h1>
    <p>Гармонический резонанс 2:1 — волна центральной спирали попадает в шаг обеих боковых спиралей</p>
    <img src="data:image/jpeg;base64,{b64}" alt="Символ Воли — Гармонизированные Спирали" />
    <div class="legend">
      <div><span class="dot" style="background:#a855f7;"></span> Центр: Фиолетовая (вдвое чаще)</div>
      <div><span class="dot" style="background:#f5b92d;"></span> По часовой: Золотая</div>
      <div><span class="dot" style="background:#10b981;"></span> Против часовой: Зелёная</div>
    </div>
  </div>
</body>
</html>
'''

with open(f'{brain_dir}\\spirals_interactive.html', 'w', encoding='utf-8') as f:
    f.write(html)

print('Updated spirals_interactive.html successfully!')
