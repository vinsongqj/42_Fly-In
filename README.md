*This project has been created as part of the 42 curriculum by vgoh*

# Fly-In

## Description

**Fly-in** is a multi-drone turn-based routing simulator. Given a map of normal, restricted, blocked or limited capacity zones, the program simulates how a fleet of drones travels from a single starting zone to a single destination zone, one turn at a time.

## Requirements

* python 3.10+
* pip

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

## Algorithm Choices and Implementation Strategy

The algorithm chosen was Yen's algorithm that would iteratively use Dijkstra's algorithm to compute the shortest path from start node to end node. Yen's algorithm was used here to find alternative routes if there are blocked zones encountered by calculating the K-shortest paths.

> "Dijkstra's algorithm finds the shortest path from one vertex to all other vertices. It does so by repeatedly selecting the nearest unvisited vertex and calculating the distance to all the unvisited neighboring vertices. Dijkstra's algorithm is often considered to be the most straightforward algorithm for solving the shortest path problem. Dijkstra's algorithm is used for solving single-source shortest path problems for directed or undirected paths. Single-source means that one vertex is chosen to be the start, and the algorithm will find the shortest path from that vertex to all other vertices." - W3Schools
>

The K-shortest paths are then implemented in the simulator to pre-compute the drone routes before running the simulation, and the drones are load-balanced to take one of these routes. Whether each drone can take the next step is computed turn by turn based on the occupancy of each zone and connection. An error should be raised if a deadlock occurs.

## Visual Representation

By default, when running without the ``--animate`` flag it should show the steps turn by turn:

<img width="418" height="323" alt="image" src="https://github.com/user-attachments/assets/28f4a62f-38b9-4c59-8103-f95ca293a852" />

Here is what it looks like with the ``--animate`` flag before running the animation:

<img width="642" height="249" alt="image-1" src="https://github.com/user-attachments/assets/0fec39c2-07d4-4c53-91c3-9486fb77c8b6" />

This is the how the map is displayed in the terminal:

<img width="413" height="262" alt="image-2" src="https://github.com/user-attachments/assets/58633959-7447-4e39-bbe2-91a983349dd1" />

The zone names are abbreviated with legends and color coded for visual clarity, and the terminal
will reset each turn at an interval of 0.5 seconds by default but can be changed with the ``--delay=`` flag to display the animation frame by frame. Drones are represented as white squares moving across the zones.

## Resources

 * [Glassbyte -
Dijkstra's Algorithm - A step by step analysis, with sample Python code](https://youtu.be/_B5cx-WD5EA?si=BKSisxV8uwMYnltF)

* [ludwig explains - 
Yen's algorithm for k shortest paths | CS 61B | Ludwig Explains ](https://youtu.be/bQCewgMFaYQ?si=B2M4CjSB1-j7yR_j)

* [ArjanCodes - This Is Why Python Data Classes Are Awesome](https://youtu.be/CvQ7e6yUtnw?si=xnLl-kyMu6v_uUST)

## Disclosure of AI usage

Claude and Gemini were used to educate myself about any further questions on the topic, handle edge cases, writing docstrings and error checking.
