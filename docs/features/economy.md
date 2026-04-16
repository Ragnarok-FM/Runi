# Economy system

## Commands
**/work** - The user can work once every hour to earn a random amount of Runes

  - Random payout range (inclusive) for /work
    
    - WORK_MIN: int = 50
    
    - WORK_MAX: int = 150
    
**/daily** - The user can use this command once every day to earn 300 Runes

  - Base payout for /daily (streak day 1)
    
    - DAILY_BASE: int = 300

  - Extra Runes added per additional streak day
    
    - DAILY_STREAK_BONUS: int = 50

  - Maximum streak that can be accumulated (caps the bonus)
    
    - DAILY_STREAK_MAX: int = 30

**/balance** - Shows the balance of Runes and active daily-streak for the user

**/richlist** - Top 10 weealthiest users

**/give** - Transfer Runes to another user

**/coinflip** - Choose heads or tails and the custom amount of Runes you want to bet
