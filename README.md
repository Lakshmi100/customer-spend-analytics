### Try testing your snowflake connection , with this script below in your bash terminal from
### your project folder

python3 -c "
from dotenv import load_dotenv
import os, snowflake.connector
load_dotenv()
conn = snowflake.connector.connect(
    account=os.getenv('SNOWFLAKE_ACCOUNT'),
    user=os.getenv('SNOWFLAKE_USER'),
    password=os.getenv('SNOWFLAKE_PASSWORD'),
    warehouse=os.getenv('SNOWFLAKE_WAREHOUSE'),
    role=os.getenv('SNOWFLAKE_ROLE'),
)
print('✓ Connected to:', conn.cursor().execute('SELECT CURRENT_VERSION()').fetchone()[0])
conn.close()
"

### U should see '✓ Connected to:' <some ip address>

### Customer Segmentation: KMeans on 24 behavioral features successfully recovered persona archetypes with ### 95-100% purity across 18 of 20 personas

![# Personas in each cluster](ml/artifacts/cluster_persona_heatmap.png)

### Coupon Ranker output

PersonaTop recommendation 

Luxury Seeker VanessaTiffany jewelry + Louis VuittonShe over-indexes 6.5x on luxury_goods and bought one today🎓 
College Student SashaStarbucks + Chipotle + Lyft15.7x coffee, 14.2x fast food, 20.5x rideshare — textbook student profile👨‍👩‍👧‍👧 
Soccer Mom LindaCostco bulk shopping5x warehouse_club affinity — exactly what a family of 4 needs👵 
Active Retiree CarolCVS pharmacy + IKEA + Spotify4.3x pharmacy spend (medications), home goods, streaming — perfect retiree profile





![Coupon Pipleine - Airflow DAG][Coupon pipeline]

[Coupon pipeline]: image.png