*This project has been created as part of the 42 curriculum by vgoh*

# Fly-In

## Description

**Fly-in** is a multi-drone turn-based routing simulator. Given a map of normal, restricted, blocked or limited capacity zones, the program simulates how a fleet of drones travels from a single starting zone to a single destination zone, one turn at a time.

The core pathfinding logic is done through Dijkstra's algorithm wrapped by Yen's algorithm to find the top-K alternate paths. Yen's algorithm will iteratively perform a Dijkstra operation to find the best alternate path if a blocked zone is encountered, while Dijkstra is in charge of determining the shortest path with the least movement cost.



## Instructions

 Before running the program, follow these steps:
 
  1.  Create a virtual environment:
  
      ```
      python3 -m venv venv
      ```
  2. Activate the virtual environment:
      ```
      source venv/bin/activate
      ```
  3. Install the dependencies:
      ```
      pip install --upgrade pip
      ```
      ```
      pip install -r requirements.txt
      ```

Now the program can be run with a few optional flags:

```
python3 main.py [path to map file] [--animate] [--delay=] [--col=] [--row=]
```

| Optional Flags  | Details |
| ------------------ |:-------------:|
| ``animate``     | Tells the program to run the simulation as an animation     |
| ``delay=``  | Seconds to delay each animation frame (default is --delay=0.5)  |
| ``col=``      | The width of the animation map (default is col=12)   |
| ``row=``      | The height of the animation map (default is row=4)   |

If run without these flags, the drone turn order will be printed out instead.


 **However, a Makefile has been created for convenience. You may run the following commands:**
 
 ```bash
 # Start a virtual environment and install the dependencies
 make install

 # Run the program
 make run ARGS="[map.txt file path] [other optional flags (refer above)]"   

 # Debug the program
 make debug

 # Run mypy and flake8 linting
 make lint

 # Run mypy with the --strict flag and flake8 linting
 make lint-strict

 # Delete all build files
 make clean
 ```