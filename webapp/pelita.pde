// @pjs preload must be used to preload the image
/* @pjs preload="agent1_80.png,agent2_80.png,agent3_80.png,agent4_80.png"; */

var stepSize = 0.5;
var angleStep = 20;

inited = false;

// Dummy wall
wall = [
  [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
  [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
  [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
  [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
  [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
  [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
  [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
  [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
  [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
  [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
  [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
  [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
  [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
];


init_game = function() {
  if (inited) return;
  agents[0] = new Agent("agent1_80.png", new Position(0,0));
  agents[1] = new Agent("agent2_80.png", new Position(0,0));
  agents[2] = new Agent("agent4_80.png", new Position(0,0));
  agents[3] = new Agent("agent3_80.png", new Position(0,0));

  inited = true;
}


function hasWall(x, y) {
  return wall[x][y] == 1;
}

function hasFood(x, y) {
  return food[x][y] == 1;
}

var gridX = wall.length;
var gridY = wall[0].length;

var scale = 30;

function scaleX(x) {
  return scale + scale * x;
}

function scaleY(y) {
  return scale + scale * y;
}

function gridToReal(x, y) {
  return [scaleX(x), scaleY(y)];
}

function Position(x, y) {
  this.x = x;
  this.y = y;
  this.equals = function(other) {
    return this.x == other.x && this.y == other.y;
  };
  this.len = function() {
    return this.distance(new Position(0, 0));
  }
  this.distance = function(other) {
    return Math.sqrt(Math.pow(this.x - other.x, 2) + Math.pow(this.y - other.y, 2));
  };
  this.toString = function() { return "{" + this.x + "; " + this.y + "}"; };
  this.clone = function() { return new Position(this.x, this.y); };
}

function Agent(img, initialPosition) {
  this.image = loadImage(img);
  this.position = initialPosition.clone();
  this.next = initialPosition.clone();

  this.food = 0;

  this.up = function() {
    this.setNext(this.next.x, this.next.y - 1);
  }
  this.down = function() {
    this.setNext(this.next.x, this.next.y + 1);
  }
  this.left = function() {
    this.setNext(this.next.x - 1, this.next.y);
  }
  this.right = function() {
    this.setNext(this.next.x + 1, this.next.y);
  }

  this.angle = 0;

  this.draw = function() {
    var x = scaleX(this.position.x - 1);
    var y = scaleY(this.position.y - 1);

    image(this.image, x, y, 50, 50);
  }

  this.needsUpdate = function() {
    return !(this.position.equals(this.next));
  };

  this.updatePosition = function(stepSize) {
    if (this.position.equals(this.next)) return;

    var update = function(current, goal, stepSize) {
      if (Math.abs(current - goal) < stepSize) {
        return goal;
      } else {
        if (current > goal) return current - stepSize;
        else return current + stepSize;
      }
    }

    var stepX = update(this.position.x, this.next.x, stepSize);
    var stepY = update(this.position.y, this.next.y, stepSize);

    this.position.x = stepX;
    this.position.y = stepY;
  };

  this.setNext = function(x, y) {
    if (hasWall(x, y)) return;
    if (hasFood(x, y)) {
      this.food += 1;
      wall[x][y] = 0;
    }
    this.next.x = x;
    this.next.y = y;
    loop();
  };

  this.put = function(x, y) {
    if (hasWall(x, y)) return;
    this.position.x = x;
    this.position.y = y;
    this.setNext(x, y);
  }
}

void drawAgent(agent) {
  var posx = agent.position.x * 30;
  var posy = agent.position.y * 30;
  agent.draw();
}

void setup() {
  size(1200, 800); //scaleX(gridX), scaleY(gridY));
  background(225);  
  fill(255);  
  //noLoop();
  PFont fontA = loadFont("courier");  
  textFont(fontA, 14);    
} 

void drawGrid() {
  pushStyle();
  stroke(187,20,20);
  fill(187,20,20);
  strokeWeight(3);
  ellipseMode(CENTER);

  for (var i=0; i<wall.length; i++) {
    for (var j=0; j<wall[i].length; j++) {
      if (hasWall(i, j)) {
        ellipse(scaleX(i), scaleY(j), 3, 3);
      }
      if (hasFood(i, j)) {
        pushStyle();
        stroke(187,187,20);
        fill(187,187,20);
        ellipse(scaleX(i), scaleY(j), 3, 3);
        popStyle();
      }
    }
  }
  popStyle();
}

void draw(){
    background(225);

    if (! inited) return;

    drawGrid();

    // determine center and max clock arm length  
    var centerX = width / 2, centerY = height / 2;  
    var maxArmLength = Math.min(centerX, centerY);
  
    for (var i=0; i<agents.length; i++) {
        agents[i].updatePosition(stepSize);
    }
 
    for (var i=0; i<agents.length; i++) {
      drawAgent(agents[i]);
    }
 
    // stop, if all are placed
    var needsUpdate = false;
    for (var i=0; i < agents.length; i++) {
      if (agents[i].needsUpdate()) { needsUpdate = true; }
    }
    
    if (! needsUpdate) noLoop();
}

