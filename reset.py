import sqlite3

# Connect to your database
conn = sqlite3.connect('database.db')
c = conn.cursor()

# Clear all votes
c.execute('DELETE FROM votes')
print("All votes deleted.")

# Allow voters to vote again
c.execute('UPDATE voters SET has_voted = 0')
print("All voters reset to 'not voted'.")

# Save changes
conn.commit()
print("Changes saved.")

# Close connection
conn.close()
print("Done!")