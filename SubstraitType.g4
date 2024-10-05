grammar SubstraitType;

//
fragment A : [aA];
fragment B : [bB];
fragment C : [cC];
fragment D : [dD];
fragment E : [eE];
fragment F : [fF];
fragment G : [gG];
fragment H : [hH];
fragment I : [iI];
fragment J : [jJ];
fragment K : [kK];
fragment L : [lL];
fragment M : [mM];
fragment N : [nN];
fragment O : [oO];
fragment P : [pP];
fragment Q : [qQ];
fragment R : [rR];
fragment S : [sS];
fragment T : [tT];
fragment U : [uU];
fragment V : [vV];
fragment W : [wW];
fragment X : [xX];
fragment Y : [yY];
fragment Z : [zZ];


If       : I F;
Then     : T H E N;
Else     : E L S E;

// TYPES
Boolean  : B O O L E A N;
I8       : I '8';
I16      : I '16';
I32      : I '32';
I64      : I '64';
FP32     : F P '32';
FP64     : F P '64';
String   : S T R I N G;
Binary   : B I N A R Y;
Timestamp: T I M E S T A M P;
TimestampTZ: T I M E S T A M P '_' T Z;
Date     : D A T E;
Time     : T I M E;
IntervalYear: I N T E R V A L '_' Y E A R;
IntervalDay: I N T E R V A L '_' D A Y;
IntervalCompound: I N T E R V A L '_' C O M P O U N D;
UUID     : U U I D;
Decimal  : D E C I M A L;
PrecisionTimestamp: P R E C I S I O N '_' T I M E S T A M P;
PrecisionTimestampTZ: P R E C I S I O N '_' T I M E S T A M P '_' T Z;
FixedChar: F I X E D C H A R;
VarChar  : V A R C H A R;
FixedBinary: F I X E D B I N A R Y;
Struct   : S T R U C T;
NStruct  : N S T R U C T;
List     : L I S T;
Map      : M A P;
ANY      : A N Y;
UserDefined: U '!';


// OPERATIONS
And      : A N D;
Or       : O R;
Assign   : ':=';

// COMPARE
Eq       : '=';
NotEquals: '!=';
Gte      : '>=';
Lte      : '<=';
Gt       : '>';
Lt       : '<';
Bang     : '!';


// MATH
Plus      : '+';
Minus : '-';
Asterisk : '*';
ForwardSlash   : '/';
Percent  : '%';

// ORGANIZE
OBracket : '[';
CBracket : ']';
OParen   : '(';
CParen   : ')';
SColon   : ';';
Comma    : ',';
QMark    : '?';
Colon    : ':';
SingleQuote: '\'';


Number
  : '-'? Int
  ;

Identifier
  : ('a'..'z' | 'A'..'Z' | '_' | '$') ('a'..'z' | 'A'..'Z' | '_' | '$' | Digit)*
  ;

LineComment
  : '//' ~[\r\n]* -> channel(HIDDEN)
  ;

BlockComment
  : (  '/*'
      ( '/'* BlockComment
      | ~[/*]
      | '/'+ ~[/*]
      | '*'+ ~[/*]
      )*
      '*'*
      '*/'
   ) -> channel(HIDDEN)
  ;

Whitespace
  : [ \t]+ -> channel(HIDDEN)
  ;

Newline
  : ( '\r' '\n'?
    | '\n'
    )
  ;


fragment Int
  : '1'..'9' Digit*
  | '0'
  ;

fragment Digit
  : '0'..'9'
  ;

start: expr EOF;

scalarType
  : Boolean #Boolean
  | I8 #i8
  | I16 #i16
  | I32 #i32
  | I64 #i64
  | FP32 #fp32
  | FP64 #fp64
  | String #string
  | Binary #binary
  | Timestamp #timestamp
  | TimestampTZ #timestampTz
  | Date #date
  | Time #time
  | IntervalYear #intervalYear
  | UUID #uuid
  | UserDefined Identifier #userDefined
  ;

parameterizedType
  : FixedChar isnull='?'? Lt len=numericParameter Gt #fixedChar
  | VarChar isnull='?'? Lt len=numericParameter Gt #varChar
  | FixedBinary isnull='?'? Lt len=numericParameter Gt #fixedBinary
  | Decimal isnull='?'? Lt precision=numericParameter Comma scale=numericParameter Gt #decimal
  | IntervalDay isnull='?'? Lt precision=numericParameter Gt #intervalDay
  | IntervalCompound isnull='?'? Lt precision=numericParameter Gt #intervalCompound
  | PrecisionTimestamp isnull='?'? Lt precision=numericParameter Gt #precisionTimestamp
  | PrecisionTimestampTZ isnull='?'? Lt precision=numericParameter Gt #precisionTimestampTZ
  | Struct isnull='?'? Lt expr (Comma expr)* Gt #struct
  | NStruct isnull='?'? Lt Identifier expr (Comma Identifier expr)* Gt #nStruct
  | List isnull='?'? Lt expr Gt #list
  | Map isnull='?'? Lt key=expr Comma value=expr Gt #map
  ;

numericParameter
  : Number #numericLiteral
  | Identifier #numericParameterName
  | expr #numericExpression
  ;

anyType: ANY;

type
  : scalarType isnull='?'?
  | parameterizedType
  | anyType isnull='?'?
  ;

//  : (OParen innerExpr CParen | innerExpr)

expr
  : OParen expr CParen #ParenExpression
  | Identifier Eq expr Newline+ (Identifier Eq expr Newline+)* finalType=type Newline* #MultilineDefinition
  | type #TypeLiteral
  | number=Number #LiteralNumber
  | identifier=Identifier isnull='?'? #TypeParam
  | Identifier OParen (expr (Comma expr)*)? CParen #FunctionCall
  | left=expr op=(And | Or | Plus | Minus | Lt | Gt | Eq | NotEquals | Lte | Gte | Asterisk | ForwardSlash) right=expr #BinaryExpr
  | If ifExpr=expr Then thenExpr=expr Else elseExpr=expr #IfExpr
  | (Bang) expr #NotExpr
  | ifExpr=expr QMark thenExpr=expr Colon elseExpr=expr #Ternary
  ;