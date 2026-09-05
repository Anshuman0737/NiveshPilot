# NiveshPilot Methodology & Mathematical Framework

## 1. Philosophy & Objectives
The mathematical core of NiveshPilot is built to optimize **investor risk-adjusted survival under uncertainty**.

For beginner retail investors, traditional mean-variance optimization or pure CAGR maximization is behaviorally flawed: a strategy that yields 16% annualized return with a 40% maximum peak-to-trough drawdown results in high rates of panic-selling, permanently destroying capital.

NiveshPilot’s objective function is:
$$\max \text{Sortino}(S) \quad \text{subject to} \quad |\text{MaxDD}(S)| \le \theta_{\text{drawdown}}$$

Where:
- $S$ is the capital deployment schedule.
- $\text{Sortino}(S) = \frac{R(S) - R_f}{\sigma_{\text{downside}}(S)}$
- $\theta_{\text{drawdown}}$ is the target downside containment threshold.

---

## 2. Market Regime Classification Logic
Regimes are classified strictly point-in-time using moving averages and volatility filters on the benchmark index:

1. **High-Volatility Regime**:
   $$\sigma_{\text{30d}} > 0.28 \implies \text{Regime} = \text{High-volatility}$$
   *Rationale*: When annualized 30-day volatility exceeds 28%, trend signals have high false-discovery rates. Immediate deployment is curtailed to 25%.

2. **Bear Regime**:
   $$P_t < \text{SMA}_{200}(t) \land \text{SMA}_{50}(t) < \text{SMA}_{200}(t) \land \text{DD}_t < -0.15 \implies \text{Regime} = \text{Bear}$$
   *Rationale*: Deep structural bear phases require capital conservation across extended tranches.

3. **Correction Regime**:
   $$P_t > \text{SMA}_{200}(t) \land -0.18 \le \text{DD}_t \le -0.05 \land R_{\text{1m}} < -0.02 \implies \text{Regime} = \text{Correction}$$
   *Rationale*: Pullbacks within larger secular bulls offer favorable entry prices. Capital is deployed in 3 tranches (40% / 30% / 30%).

4. **Recovery Regime**:
   $$\text{DD}_t < -0.10 \land P_t > \text{SMA}_{50}(t) \land R_{\text{1m}} > 0.03 \implies \text{Regime} = \text{Recovery}$$
   *Rationale*: Early rebound out of deep drawdowns warrants 60% immediate deployment to secure low-cost basis.

5. **Bull Regime**:
   $$P_t > \text{SMA}_{200}(t) \land \text{SMA}_{50}(t) \ge \text{SMA}_{200}(t) \land R_{\text{3m}} > 0 \implies \text{Regime} = \text{Bull}$$
   *Rationale*: Calm upward trends warrant high immediate participation (70%) with a modest 30% buffer.

---

## 3. Decision Regret Formulation
For any historical decision point $t$, we compute the counterfactual outcomes across all baselines:
- $R_A$: Return under 100% Immediate Lump Sum
- $R_B$: Return under 50/50 Staggered Deployment
- $R_E$: Return under NiveshPilot Adaptive Strategy

The **Decision Regret** relative to Lump Sum is defined as:
$$\text{Regret}_{\text{Lump}}(t) = R_A(t) - R_E(t)$$

- When $\text{Regret} > 0$: The investor forewent upside by staggering into a strong bull market.
- When $\text{Regret} < 0$: The investor saved capital and avoided drawdown by withholding full deployment during a market crash.
