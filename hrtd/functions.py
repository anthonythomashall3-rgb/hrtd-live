# 1116: a copy of the Mac's 964/code/functions_964.py (the rules, nothing else), for series GitHub adds itself.
"""964 (no AI): the function of every series, by fixed written rules on its title and release.
Functions are numbered by economic relevance (Anthony, 31 Oct 2026: "order this based on economic relevance"):
the headline cycle measures first (output, jobs, unemployment, income and spending, production, prices, rates, credit),
then the rest. The RULES are checked in the order written (most specific first); the first match wins.
Writes 01_catalog/functions.csv (function list) and 01_catalog/series_functions.csv (series -> function, rule hit)."""
import re, pandas as pd
FUNCTIONS = ['Output & GDP', 'Business Cycle & Recession Indicators', 'Employment & Payrolls', 'Unemployment & Jobless Claims', 'Income & Consumer Spending',
             'Industrial Production & Manufacturing', 'Inflation & Prices', 'Interest Rates & Yields',
             'Credit, Lending & Debt', 'Money, Banking & Reserves', 'Business & Consumer Surveys', 'Housing & Construction',
             'Stock, Bond & Currency Markets', 'Wages, Hours & Labor Costs', 'Business Sales, Inventories & Profits',
             'International Trade & Payments', 'Government Finance & Taxes', 'Productivity',
             'Energy, Agriculture & Commodities', 'Financial Accounts & Wealth', 'Population & Migration',
             'Poverty & Income Distribution', 'Business Formation & Innovation', 'Education', 'Health',
             'Transportation', 'Environment', 'Crime & Public Safety']
NUM = {f: f'{i + 1:02d} {f}' for i, f in enumerate(FUNCTIONS)}
NUM['Unclassified'] = '99 Unclassified'
RULES = [  # (function, pattern), first match wins; titles are judged first, the release name only if no title rule hits
    ('Business Cycle & Recession Indicators', r'recession|coincident|leading index|leading indicator|economic conditions ind|gdpnow|nowcast|sahm|uncertainty|business cycle|midwest economy index|activity index|financial stress|financial conditions|distress index|hiring indicator'),
    ('Crime & Public Safety', r'offenses|crime|violent|burglary|larceny|robbery|homicide|arrests'),
    ('Business & Consumer Surveys', r'diffusion index|sentiment|consumer confidence|business confidence|ceo confidence|business outlook|manufacturing survey|outlook survey|business conditions|purchasing managers|\bism\b|manufacturing index|services index'),
    ('Inflation & Prices', r'consumer price index|\bcpi\b|producer price index|price index for personal consumption'),
    ('Poverty & Income Distribution', r'poverty|inequality|gini|income distribution|income quintile|share of aggregate income|disconnected youth|burdened households|racial dissimilarity|SNAP benefits|food stamp'),
    ('Unemployment & Jobless Claims', r'unemploy|jobless|initial claims|continued claims|insured claims|labor underutilization|\bU-?6\b|pandemic claims'),
    ('Wages, Hours & Labor Costs', r'employment cost|earnings|wage|salar|compensation|\bhours\b|minimum wage|labor cost|labor share'),
    ('Productivity', r'productivity|output per hour|total factor|multifactor'),
    ('Employment & Payrolls', r'job openings|hires|quits|layoffs|separations|all employees|nonfarm|payroll|employ(?!er firms)|labor force|participation rate|job postings|establishments? count'),
    # 964 (2026-11-01, measured): every housing term must START a word (\b...): 'rent' matched inside 'Current' (and 'Current
    # Business', 'current receipts'), 'parent' (Single-parent households), 'housing' inside 'Warehousing', 'construction' inside
    # 'Reconstruction' - the fix takes 6,888 series (net) out of this function (938 of 1,087 scan729 series); 'nonresidential' is construction, named
    ('Housing & Construction', r'\b(?:additions and alterations|plans filed|value of plans|house price|home price|home value|zillow|housing|home ?owner|residential|nonresidential|building permit|housing starts|new homes?|construction|realtor|rental vacancy|rent\b|homeownership|case-shiller|listing|market hotness|mortgage delinquen)'),
    ('Inflation & Prices', r'price index|consumer price|\bcpi\b|producer price|\bppi\b|deflator|inflation|average price|import price|export price|price of|prices paid|cost of living'),
    ('Output & GDP', r'gross domestic product|\bgdp\b|gross national product|\bgnp\b|real output|gross state product|value added|final sales|gross output|national income'),
    ('Poverty & Income Distribution', r'median household income|mean household'),
    ('Income & Consumer Spending', r'personal income|disposable|personal consumption|consumer expenditure|consumption expenditure|retail sales|retail trade|food services|personal saving|per capita personal|transfer receipts|consumer spending'),
    ('Industrial Production & Manufacturing', r'production|built for|\bbuilt\b|locomotive|pig iron|steel ingot|freight cars|industrial production|capacity utilization|manufactur|durable goods|new orders|shipments|\bm3\b|industrial output'),
    ('Interest Rates & Yields', r'interest rate|secured overnight|overnight financing|rate cap|\byield|treasury bill|treasury constant|bond rate|mortgage rate|federal funds|prime rate|discount rate|libor|sofr|\brate on\b|commercial paper|basis points|spread'),
    ('Credit, Lending & Debt', r'loan|credit|debt|delinquen|charge-off|lending|borrow|finance compan|consumer credit'),
    ('Money, Banking & Reserves', r'money stock|monetary services|failures and assistance|bank failure|\bm1\b|\bm2\b|monetary base|reserve|deposit|bank|currency in circulation|factors affecting|federal reserve notes|savings institution'),
    ('Stock, Bond & Currency Markets', r'stock|value of the dollar|bond prices|equity|equities|nasdaq|s&p|dow jones|wilshire|volatility|\bvix\b|exchange rate|dollar index|bofa|total return|index data|securities|market value'),
    ('Business Sales, Inventories & Profits', r'net operating income|net income|inventor|wholesale|sales|revenue|profit|quarterly financial report|services survey|service annual|economic survey|receipts of'),
    ('International Trade & Payments', r'export|import|trade balance|international|current account|balance of payments|foreign|tariff|exporters'),
    ('Government Finance & Taxes', r'\btax|government|federal debt|outlays|federal receipts|deficit|surplus|public debt|\bsoi\b'),
    ('Environment', r'emission|\bco2\b|carbon|pollut'),
    ('Energy, Agriculture & Commodities', r'milk|butter|eggs|cattle|hogs|cotton|spot price|cotton|farm|agricultur|crop|livestock|\boil\b|crude|gasoline|diesel|natural gas|electric|energy|coal|commodit|gold|wheat|corn|copper'),
    ('Financial Accounts & Wealth', r'financial accounts|flow of funds|net worth|assets|liabilities|wealth|households and nonprofit|rest of the world|z\.1'),
    ('Business Formation & Innovation', r'business formation|business applications|patent|trademark|startups?|new businesses'),
    ('Education', r'education|attainment|school|degree|bachelor|college'),
    ('Health', r'health|medicare|medicaid|hospital|mortality|death|disabilit|insurance coverage|uninsured|covid|birth'),
    ('Transportation', r'telegraph|telephone|messages sent|passenger|commute|transport|vehicle miles|freight|airline|air passenger|rail|truck|\btsi\b|traffic'),
    ('Population & Migration', r'population|migration|resident|\bage\b|median age|households\b|census'),
    ('Business & Consumer Surveys', r'survey|sentiment|outlook|business conditions|confidence|diffusion index|opinion'),
]
CRE = [(f, re.compile(p, re.I)) for f, p in RULES]
# releases that are one function whatever the series title says (checked before the title rules)
WHOLE_RELEASE = [
    ('Business & Consumer Surveys', r'Outlook Survey$|Manufacturing Survey$|Business Outlook Survey|Business Leaders Survey|Survey of Consumers|Fifth District Survey|Manufacturing Index$|Services Survey$|Composite Index$'),
    ('Income & Consumer Spending', r'^Consumer Expenditure Surveys$'),
    ('Poverty & Income Distribution', r'^Small Area Income and Poverty Estimates$'),
    ('Financial Accounts & Wealth', r'^Z\.1 Financial Accounts|^Distributional Financial Accounts'),
    ('Productivity', r'^Industry Productivity$|^Total Factor Productivity'),
    ('International Trade & Payments', r'^Treasury International Capital|^Number of Exporters'),
    ('Money, Banking & Reserves', r'^H\.4\.1 |^H\.8 |^Banking and Monetary Statistics|^Reports of Condition and Income|^H\.6 |^H\.3 '),
    ('Stock, Bond & Currency Markets', r'^Nasdaq |^ICE BofA|^Coinbase'),
    ('Housing & Construction', r'^Housing Inventory Core Metrics$|^Market Hotness Index$'),
    ('Population & Migration', r'^County Population Estimates By Race|^Annual Estimates of the Population|^Net Migration Flows'),
    ('Credit, Lending & Debt', r'^Equifax Credit Quality'),
    ('Business Sales, Inventories & Profits', r'^Annual Integrated Economic Survey|^Service Annual Survey|^Quarterly Services Survey|^Quarterly Financial Report'),
    ('Business Cycle & Recession Indicators', r'Labor Market Conditions Indicators|Risk-On Risk-Off|Global Real Economic Activity|Tech Pulse|Price Pressures|Summary of Economic Projections|Policy Rate Skew'),
    ('Interest Rates & Yields', r'Tri-Party General Collateral|Optimal Blue Mortgage|Temporary Open Market'),
    ('Income & Consumer Spending', r'Visa Spending Momentum|Supplemental Estimates, Motor Vehicles'),
    ('Money, Banking & Reserves', r'Currency and Coin Services|Money Zero Maturity'),
    ('Government Finance & Taxes', r'Monthly Treasury Statement'),
    ('Output & GDP', r'Penn World Table'),
]
WRE = [(f, re.compile(p)) for f, p in WHOLE_RELEASE]

def classify(title, release):
    for i, (f, c) in enumerate(WRE):
        if c.search(release or ''): return f, 200 + i
    for i, (f, c) in enumerate(CRE):
        if c.search(title or ''): return f, i
    if PRINTED.search(release or ''): return 'Unclassified', -2   # a printed compilation's name says nothing of a row's function
    for i, (f, c) in enumerate(CRE):
        if c.search(release or ''): return f, 100 + i
    return 'Unclassified', -1
# 964 (2026-11-01, measured): printed compilations of many tables (729's row parses) are NOT judged by their release name: 'Survey
# of Current Business' sent 909 scan729 rows to Housing ('rent' in 'Current'; with the word fix it would send them to Surveys),
# 'Federal Reserve Bulletin' 610 to Money & Banking ('reserve'), 'Employment and Earnings' 392 to Wages ('earnings'), whatever the row
PRINTED = re.compile(r'^(Survey of Current Business|Federal Reserve Bulletin|Employment and Earnings|Monthly Labor Review|Business Conditions Digest|Employment and Payrolls)$')

