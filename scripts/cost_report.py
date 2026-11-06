"""Compute measured provider costs; unknown token usage/prices are never zero-cost."""
import argparse
from contextlib import closing
from decimal import Decimal
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage import connect
from database import Database


def report(rows, prices, learners, fx, fixed_uzs, margin):
    if learners <= 0 or fx <= 0 or fixed_uzs < 0 or not 0 <= margin < 1:
        raise ValueError('Check learners, exchange rate, fixed costs and margin')
    known_usd = Decimal(0)
    unknown = 0
    for model, input_tokens, output_tokens, calls in rows:
        price = prices.get(model, {})
        if input_tokens is None or output_tokens is None or price.get('input_per_million_usd') is None or price.get('output_per_million_usd') is None:
            unknown += calls
            continue
        rates = [Decimal(str(price[key])) for key in ('input_per_million_usd', 'output_per_million_usd')]
        if any(rate < 0 for rate in rates):
            raise ValueError('Negative token prices are invalid')
        known_usd += (input_tokens*rates[0] + output_tokens*rates[1])/Decimal(1000000)
    result = {'provider_attempts':sum(row[3] for row in rows), 'unknown_attempts':unknown,
              'known_api_usd':str(known_usd), 'learners':learners,
              'cost_per_learner_uzs':None, 'price_for_target_gross_margin_uzs':None}
    if not unknown:
        unit = (known_usd*fx+fixed_uzs)/learners
        result.update(cost_per_learner_uzs=str(unit), price_for_target_gross_margin_uzs=str(unit/(1-margin)))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('prices','start','end','learners','usd-uzs','fixed-uzs','margin'):
        p.add_argument('--'+name, required=True)
    a = p.parse_args()
    with closing(connect(Database().db_path)) as conn:
        # Group unknown usage separately so SUM cannot conceal missing provider metadata.
        rows = conn.execute("""SELECT model,CASE WHEN MIN(input_tokens IS NOT NULL AND output_tokens IS NOT NULL)=0 THEN NULL ELSE SUM(input_tokens) END,CASE WHEN MIN(input_tokens IS NOT NULL AND output_tokens IS NOT NULL)=0 THEN NULL ELSE SUM(output_tokens) END,COUNT(*) FROM ai_usage
            WHERE created_at>=? AND created_at<? GROUP BY model,(input_tokens IS NULL OR output_tokens IS NULL)""",(a.start,a.end)).fetchall()
    result = report(rows, json.loads(Path(a.prices).read_text()), int(a.learners), Decimal(a.usd_uzs), Decimal(a.fixed_uzs), Decimal(a.margin))
    if not rows:
        result.update(cost_per_learner_uzs=None, price_for_target_gross_margin_uzs=None, note='No measurements yet')
    print(json.dumps(result, ensure_ascii=False, indent=2))
