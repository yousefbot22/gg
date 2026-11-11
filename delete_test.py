import sqlite3

c = sqlite3.connect('data/answers.db')
c.execute("DELETE FROM group_members WHERE group_id = ?", ('tst',))
c.execute("DELETE FROM subscription_groups WHERE group_id = ?", ('tst',))
c.commit()
c.close()
print("✅ Deleted tst group")