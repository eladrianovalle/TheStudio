#!/ python
from studio.crew import StudioCrew

def run():
    # Start with a simple idea
    inputs = {'game_idea': 'A 3D stealth horror roguelike for the web'}
    
    print("--- 🟢 ENTERING MARKET ROOM ---")
    result = StudioCrew(phase='market').crew().kickoff(inputs=inputs)
    
    print("\n\n--- 🏆 FINAL OUTPUT ---")
    print(result)

if __name__ == "__main__":
   run()